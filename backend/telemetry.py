"""
Backend Telemetry for Medical Mirror Observer
==============================================

Emits OBSERVER_TELEMETRY events via:
1. WebSocket to frontend (which can re-broadcast to Observer extension)
2. Direct HTTP POST to Observer server (reliable backup)

Pipeline Position: [4-6/7]
  interceptor.js -> injector.js -> background.js -> [main.py] ->
  [fhir_converter.py] -> [WebSocket] -> SurgicalDashboard.tsx
"""

from datetime import datetime
from typing import Optional, Dict, Any
import logging
import httpx
import asyncio

logger = logging.getLogger("shadow-ehr")

# Observer server URL for direct HTTP telemetry
OBSERVER_URL = "http://localhost:3000"

# Global reference to broadcast function (set by main.py)
_broadcast_fn = None


def set_broadcast_function(fn):
    """Set the broadcast function for sending telemetry to frontend."""
    global _broadcast_fn
    _broadcast_fn = fn


async def emit_telemetry(
    stage: str,
    action: str,
    success: bool = True,
    data: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None,
    correlation_id: Optional[str] = None
):
    """
    Emit telemetry event to Observer via two channels:
    1. WebSocket broadcast to frontend (if connected)
    2. Direct HTTP POST to Observer server (reliable backup)

    Args:
        stage: Pipeline stage (backend, fhir-converter, websocket)
        action: What happened (ingest, process, convert, broadcast)
        success: Whether the action succeeded
        data: Stage-specific data (url, patientId, recordType, etc.)
        duration_ms: Processing time in milliseconds
        correlation_id: ID to correlate events across pipeline
    """
    event = {
        "type": "OBSERVER_TELEMETRY",
        "source": "athena-scraper",
        "event": {
            "stage": stage,
            "action": action,
            "success": success,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    }

    if data:
        event["event"]["data"] = data
    if duration_ms is not None:
        event["event"]["duration_ms"] = duration_ms
    if correlation_id:
        event["event"]["correlationId"] = correlation_id

    # Channel 1: WebSocket broadcast to frontend
    if _broadcast_fn:
        try:
            await _broadcast_fn(event)
            logger.debug(f"Telemetry broadcast: {stage}/{action}")
        except Exception as e:
            logger.debug(f"Telemetry broadcast failed: {e}")

    # Channel 2: Direct HTTP POST to Observer server (non-blocking)
    asyncio.create_task(_post_to_observer(event, stage, action))


async def _post_to_observer(event: dict, stage: str, action: str):
    """
    Post telemetry event directly to Observer server.
    Non-blocking, fails silently - Observer is optional.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{OBSERVER_URL}/api/events",
                json=event
            )
            logger.debug(f"Telemetry posted to Observer: {stage}/{action}")
    except Exception as e:
        # Silent fail - Observer is optional, don't affect main flow
        logger.debug(f"Observer POST failed (optional): {e}")


class TelemetryTimer:
    """Context manager for timing operations and emitting telemetry."""

    def __init__(
        self,
        stage: str,
        action: str,
        data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ):
        self.stage = stage
        self.action = action
        self.data = data or {}
        self.correlation_id = correlation_id
        self.start_time = None
        self.success = True

    async def __aenter__(self):
        self.start_time = datetime.utcnow()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (datetime.utcnow() - self.start_time).total_seconds() * 1000

        if exc_type:
            self.success = False
            self.data["errorMessage"] = str(exc_val)

        await emit_telemetry(
            stage=self.stage,
            action=self.action,
            success=self.success,
            data=self.data,
            duration_ms=duration_ms,
            correlation_id=self.correlation_id
        )

        return False  # Don't suppress exceptions


# =============================================================================
# DATA COMPLETENESS TRACKING
# =============================================================================

# Expected fields for data quality assessment
# Priority: critical (blocks surgery), important (affects decisions), optional
EXPECTED_FIELDS = {
    "patient_basic": {
        "critical": ["mrn", "name", "dob"],
        "important": ["gender", "conditions", "medications"],
        "optional": ["vitals", "notes", "lastEncounter"]
    },
    "vascular_profile": {
        "critical": [
            "patient_id", "mrn", "name",
            "antithrombotics", "high_bleeding_risk"
        ],
        "important": [
            "diagnoses", "renal_function", "coagulation",
            "cardiac_clearance", "critical_allergies",
            "contrast_caution", "cardiac_risk"
        ],
        "optional": [
            "documents", "vascular_history"
        ]
    },
    "preop_checklist": {
        "critical": [
            "patient_id", "mrn", "ready_for_surgery",
            "blocking_issues"
        ],
        "important": [
            "antithrombotics_held", "bridging_required",
            "renal_function_ok", "coagulation_ok",
            "cardiac_cleared", "contrast_allergy"
        ],
        "optional": [
            "anticoagulant_details", "renal_details",
            "coagulation_details", "cardiac_details",
            "allergy_alerts"
        ]
    },
    "clinical_document": {
        "critical": ["id", "title", "type", "date"],
        "important": ["provider", "summary"],
        "optional": ["url", "findings"]
    }
}


def assess_data_completeness(data: dict, data_type: str) -> dict:
    """
    Assess completeness of a data object against expected fields.

    Args:
        data: The data object to assess
        data_type: Type of data (patient_basic, vascular_profile, etc.)

    Returns:
        dict with completeness metrics:
        {
            "data_type": "vascular_profile",
            "score": 72,  # 0-100 completeness score
            "present": ["mrn", "name", ...],
            "missing": {
                "critical": ["antithrombotics"],
                "important": ["renal_function"],
                "optional": []
            },
            "empty": ["diagnoses"],  # Present but empty/null
            "quality_issues": ["Critical: antithrombotics not found"]
        }
    """
    if data_type not in EXPECTED_FIELDS:
        return {"error": f"Unknown data type: {data_type}"}

    schema = EXPECTED_FIELDS[data_type]

    present = []
    missing = {"critical": [], "important": [], "optional": []}
    empty = []
    quality_issues = []

    # Check each priority level
    for priority in ["critical", "important", "optional"]:
        for field in schema.get(priority, []):
            if field in data:
                value = data[field]
                # Check if present but empty
                if value is None or value == "" or value == [] or value == {}:
                    empty.append(field)
                    if priority == "critical":
                        quality_issues.append(f"CRITICAL: {field} is empty")
                    elif priority == "important":
                        quality_issues.append(f"Important: {field} is empty")
                else:
                    present.append(field)
            else:
                missing[priority].append(field)
                if priority == "critical":
                    quality_issues.append(f"CRITICAL: {field} not found")
                elif priority == "important":
                    quality_issues.append(f"Important: {field} not found")

    # Calculate score
    # Critical fields worth 3 points, important 2, optional 1
    total_points = (
        len(schema.get("critical", [])) * 3 +
        len(schema.get("important", [])) * 2 +
        len(schema.get("optional", [])) * 1
    )

    earned_points = 0
    for field in present:
        if field in schema.get("critical", []):
            earned_points += 3
        elif field in schema.get("important", []):
            earned_points += 2
        else:
            earned_points += 1

    # Deduct partial points for empty fields
    for field in empty:
        if field in schema.get("critical", []):
            earned_points -= 1.5  # Half credit for empty critical
        elif field in schema.get("important", []):
            earned_points -= 1

    score = int((earned_points / total_points) * 100) if total_points > 0 else 0
    score = max(0, min(100, score))  # Clamp to 0-100

    return {
        "data_type": data_type,
        "score": score,
        "present": present,
        "missing": missing,
        "empty": empty,
        "quality_issues": quality_issues,
        "total_fields": len(schema.get("critical", [])) + len(schema.get("important", [])) + len(schema.get("optional", [])),
        "present_count": len(present),
        "missing_critical_count": len(missing["critical"]),
        "missing_important_count": len(missing["important"])
    }


async def emit_data_quality(
    patient_id: str,
    data_type: str,
    data: dict,
    correlation_id: Optional[str] = None
):
    """
    Assess data completeness and emit telemetry to Observer.

    This allows the Observer to:
    1. Track which data fields are consistently missing
    2. Generate recommendations for improving data capture
    3. Identify patients with incomplete records

    Args:
        patient_id: Patient identifier
        data_type: Type of data being assessed
        data: The data object to assess
        correlation_id: Optional correlation ID
    """
    assessment = assess_data_completeness(data, data_type)

    # Log quality issues locally
    if assessment.get("quality_issues"):
        for issue in assessment["quality_issues"][:3]:  # Log first 3
            logger.warning(f"[{patient_id}] Data Quality: {issue}")

    # Emit telemetry event
    await emit_telemetry(
        stage="data-quality",
        action="assessment",
        success=assessment.get("score", 0) >= 70,  # Success if 70%+ complete
        data={
            "patientId": str(patient_id),
            "dataType": data_type,
            "completenessScore": assessment.get("score", 0),
            "presentCount": assessment.get("present_count", 0),
            "totalFields": assessment.get("total_fields", 0),
            "missingCritical": assessment.get("missing", {}).get("critical", []),
            "missingImportant": assessment.get("missing", {}).get("important", []),
            "emptyFields": assessment.get("empty", []),
            "qualityIssues": assessment.get("quality_issues", [])
        },
        correlation_id=correlation_id
    )

    return assessment


async def emit_transfer_summary(
    patient_id: str,
    source: str,
    destination: str,
    data_transferred: dict,
    data_requested: list,
    correlation_id: Optional[str] = None
):
    """
    Emit telemetry about what data was transferred vs what was expected.

    This tracks:
    - What data was requested/needed
    - What data was actually available and transferred
    - What gaps exist in the data pipeline

    Args:
        patient_id: Patient identifier
        source: Where data came from (athena, cache, fhir)
        destination: Where data went (webui, fhir-store, etc.)
        data_transferred: Dict with field names and presence (True/False/None)
        data_requested: List of field names that were requested
        correlation_id: Optional correlation ID
    """
    # Calculate what's missing
    transferred = [k for k, v in data_transferred.items() if v not in [None, "", [], {}]]
    missing = [f for f in data_requested if f not in transferred]

    transfer_rate = len(transferred) / len(data_requested) * 100 if data_requested else 100

    await emit_telemetry(
        stage="data-transfer",
        action="summary",
        success=transfer_rate >= 80,
        data={
            "patientId": str(patient_id),
            "source": source,
            "destination": destination,
            "requested": data_requested,
            "transferred": transferred,
            "missing": missing,
            "transferRate": round(transfer_rate, 1),
            "gapCount": len(missing)
        },
        correlation_id=correlation_id
    )
