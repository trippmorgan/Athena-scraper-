"""
Backend Telemetry for Medical Mirror Observer
==============================================

Emits OBSERVER_TELEMETRY events via WebSocket to frontend,
which re-broadcasts them via postMessage for the Observer extension.

Pipeline Position: [4-6/7]
  interceptor.js -> injector.js -> background.js -> [main.py] ->
  [fhir_converter.py] -> [WebSocket] -> SurgicalDashboard.tsx
"""

from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger("shadow-ehr")

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
    Emit telemetry event to frontend for Observer capture.

    Args:
        stage: Pipeline stage (backend, fhir-converter, websocket)
        action: What happened (ingest, process, convert, broadcast)
        success: Whether the action succeeded
        data: Stage-specific data (url, patientId, recordType, etc.)
        duration_ms: Processing time in milliseconds
        correlation_id: ID to correlate events across pipeline
    """
    if not _broadcast_fn:
        logger.debug(f"Telemetry skipped (no broadcast fn): {stage}/{action}")
        return

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

    try:
        await _broadcast_fn(event)
        logger.debug(f"Telemetry emitted: {stage}/{action}")
    except Exception as e:
        # Silent fail - observer is optional
        logger.debug(f"Telemetry emit failed: {e}")


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
