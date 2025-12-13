"""Event store for raw AthenaNet traffic and interpreter index metadata."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class EventStore:
    """Append-only JSONL storage for intercepted events and interpreter index entries."""

    def __init__(self, root: Path | str = Path("data")):
        self.root = Path(root)
        self.raw_path = self.root / "raw_events.jsonl"
        self.index_path = self.root / "event_index.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger("shadow-ehr")

    async def append_raw_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Store a raw intercepted event and return the normalized record."""

        normalized = {
            "id": event.get("id") or str(uuid.uuid4()),
            "timestamp": event.get("timestamp") or datetime.utcnow().isoformat(),
            "endpoint": event.get("endpoint", ""),
            "method": (event.get("method") or "GET").upper(),
            "status": event.get("status"),
            "patient_id": event.get("patient_id"),
            "payload_size": event.get("payload_size", 0),
            "payload": event.get("payload"),
            "source": event.get("source", "unknown"),
        }

        async with self._lock:
            with self.raw_path.open("a") as f:
                f.write(json.dumps(normalized) + "\n")

        self._logger.debug(
            "Raw event appended: %s %s (patient=%s)"
            % (
                normalized["method"],
                normalized["endpoint"][:60],
                normalized.get("patient_id") or "unknown",
            )
        )
        return normalized

    async def append_index_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Store a lightweight interpreter index entry linked to a raw event."""

        normalized = {
            "event_id": entry.get("event_id"),
            "timestamp": entry.get("timestamp") or datetime.utcnow().isoformat(),
            "patient_id": entry.get("patient_id"),
            "record_type": entry.get("record_type", "unknown"),
            "endpoint": entry.get("endpoint", ""),
            "notes": entry.get("notes", ""),
        }

        async with self._lock:
            with self.index_path.open("a") as f:
                f.write(json.dumps(normalized) + "\n")

        self._logger.debug(
            "Index entry appended: event=%s type=%s patient=%s",
            normalized.get("event_id"),
            normalized["record_type"],
            normalized.get("patient_id") or "unknown",
        )
        return normalized

    def get_raw_events(self, patient_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent raw events, optionally filtered by patient."""

        return self._read_jsonl(self.raw_path, patient_id=patient_id, limit=limit)

    def get_index(self, patient_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent interpreter index entries."""

        return self._read_jsonl(self.index_path, patient_id=patient_id, limit=limit)

    def _read_jsonl(self, path: Path, patient_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []

        records: List[Dict[str, Any]] = []
        with path.open() as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if patient_id and record.get("patient_id") != patient_id:
                        continue
                    records.append(record)
                except json.JSONDecodeError:
                    continue

        return records[-limit:]
