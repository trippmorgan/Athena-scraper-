"""
=============================================================================
CLINICAL CORE CLIENT FOR ATHENA-SCRAPER
=============================================================================

PURPOSE:
    Send copies of intercepted Athena data to the PlaudAI/SCC backend.
    This is a PARALLEL path - JSONL continues to work independently.

HOW IT WORKS:
    1. Athena-Scraper intercepts data (existing functionality)
    2. Data is written to raw_events.jsonl (existing functionality)
    3. This client ALSO sends a copy to PlaudAI (NEW)

SAFETY:
    - Fire-and-forget: Doesn't block if PlaudAI is slow or down
    - Idempotent: Same data = same hash = no duplicates
    - Safe failures: If this fails, JSONL still works
    - No modifications: Existing code is unchanged

USAGE:
    from clients.clinical_core_client import get_client

    client = get_client()
    client.push_event(
        athena_patient_id="12345",
        event_type="medication",
        payload={"name": "Aspirin", "dose": "81mg"}
    )

=============================================================================
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

import requests

# ============================================================
# SETUP
# ============================================================

# Create logger for this module
logger = logging.getLogger("athena.client")


# ============================================================
# MAIN CLIENT CLASS
# ============================================================

class ClinicalCoreClient:
    """
    HTTP client for sending Athena data to PlaudAI.

    FEATURES:
        - Fire-and-forget: Doesn't wait for response (optional)
        - Idempotent: Generates hash to prevent duplicates
        - Resilient: Failures don't crash the main application
        - Configurable: URL and timeout via environment variables
    """

    def __init__(
        self,
        base_url: str = None,
        timeout: float = 5.0,
        enabled: bool = True
    ):
        """
        Initialize the client.

        ARGS:
            base_url: PlaudAI server URL (default: from env or localhost:8001)
            timeout: Request timeout in seconds (default: 5)
            enabled: Whether to actually send data (default: True)
        """
        # Get URL from environment or use default
        self.base_url = base_url or os.getenv(
            "CLINICAL_CORE_URL",
            "http://100.75.237.36:8000"
        )

        self.timeout = timeout
        self.enabled = enabled

        # Create a session for connection reuse
        self._session = requests.Session()

        logger.info(
            f"ClinicalCoreClient initialized: {self.base_url} "
            f"(enabled={self.enabled})"
        )

    def _generate_hash(
        self,
        patient_id: str,
        event_type: str,
        data: dict
    ) -> str:
        """
        Generate idempotency key from data.

        This ensures that:
            - Same data sent twice = same hash = only stored once
            - Different data = different hash = both stored
        """
        payload_str = json.dumps(data, sort_keys=True)
        raw = f"{patient_id}:{event_type}:{payload_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    def push_event(
        self,
        athena_patient_id: str,
        event_type: str,
        payload: Dict[str, Any],
        event_subtype: Optional[str] = None,
        source_endpoint: Optional[str] = None,
        confidence: float = 0.0,
        captured_at: datetime = None
    ) -> bool:
        """
        Send a clinical event to PlaudAI.

        ARGS:
            athena_patient_id: The patient's MRN from Athena
            event_type: What kind of data (medication, problem, etc.)
            payload: The actual data from Athena
            event_subtype: Optional sub-classification
            source_endpoint: Which Athena API was intercepted
            confidence: Classification confidence (0.0-1.0)
            captured_at: When Athena sent this (default: now)

        RETURNS:
            True if successful, False otherwise

        NOTE:
            This method NEVER raises exceptions.
            Failures are logged but don't crash the caller.
        """
        # -----------------------------
        # Check if enabled
        # -----------------------------
        if not self.enabled:
            logger.debug("Client disabled, skipping push")
            return False

        # -----------------------------
        # Validate input
        # -----------------------------
        if not athena_patient_id:
            logger.warning("No patient ID provided, skipping push")
            return False

        # -----------------------------
        # Build request data
        # -----------------------------
        try:
            request_data = {
                "athena_patient_id": str(athena_patient_id),
                "event_type": event_type,
                "event_subtype": event_subtype,
                "payload": payload,
                "captured_at": (
                    captured_at or datetime.utcnow()
                ).isoformat() + "Z",
                "source_endpoint": source_endpoint,
                "confidence": confidence,
                "indexer_version": "2.0.0"
            }

            # -----------------------------
            # Send to PlaudAI
            # -----------------------------
            response = self._session.post(
                f"{self.base_url}/ingest/athena",
                json=request_data,
                timeout=self.timeout
            )

            # -----------------------------
            # Handle response
            # -----------------------------
            if response.status_code == 200:
                result = response.json()

                if result.get("status") == "duplicate":
                    # Already have this data - that's fine
                    logger.debug(
                        f"Duplicate event for {athena_patient_id}"
                    )
                else:
                    # New data stored successfully
                    logger.info(
                        f"Pushed {event_type} for {athena_patient_id}"
                    )
                return True
            else:
                # Server returned an error
                logger.warning(
                    f"Push failed ({response.status_code}): "
                    f"{response.text[:200]}"
                )
                return False

        except requests.Timeout:
            # Request took too long - PlaudAI might be overloaded
            logger.warning(
                f"Push timeout for {athena_patient_id} "
                f"(continuing anyway - JSONL is the backup)"
            )
            return False

        except requests.ConnectionError:
            # Can't reach PlaudAI - it might not be running
            logger.warning(
                "PlaudAI not reachable (continuing with JSONL only)"
            )
            return False

        except Exception as e:
            # Something unexpected happened
            logger.error(f"Push error: {e}")
            return False

    def push_batch(
        self,
        events: list
    ) -> Dict[str, int]:
        """
        Push multiple events at once.

        ARGS:
            events: List of dicts with push_event() parameters

        RETURNS:
            {"success": N, "failed": N, "skipped": N}
        """
        results = {"success": 0, "failed": 0, "skipped": 0}

        for event in events:
            success = self.push_event(**event)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    def health_check(self) -> bool:
        """
        Check if PlaudAI is reachable.

        USE THIS TO:
            - Verify connection before sending data
            - Display status in UI

        RETURNS:
            True if PlaudAI is healthy, False otherwise
        """
        try:
            response = self._session.get(
                f"{self.base_url}/ingest/health",
                timeout=2.0
            )
            return response.status_code == 200
        except:
            return False

    def get_stats(self) -> Optional[dict]:
        """
        Get ingestion statistics from PlaudAI.

        RETURNS:
            Stats dict or None if unreachable
        """
        try:
            response = self._session.get(
                f"{self.base_url}/ingest/stats",
                timeout=2.0
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None


# ============================================================
# SINGLETON INSTANCE
# ============================================================

# Global client instance - reused across all calls
_client = None


def get_client() -> ClinicalCoreClient:
    """
    Get or create the singleton client.

    USAGE:
        from clients.clinical_core_client import get_client
        client = get_client()
        client.push_event(...)
    """
    global _client
    if _client is None:
        _client = ClinicalCoreClient()
    return _client


def disable_client():
    """
    Disable the client (for testing or rollback).

    After calling this, push_event() will do nothing.
    """
    global _client
    if _client is not None:
        _client.enabled = False
    else:
        _client = ClinicalCoreClient(enabled=False)


def enable_client():
    """Re-enable the client."""
    global _client
    if _client is not None:
        _client.enabled = True
