"""
Provenance: Medico-Legal Traceability for Clinical Data

This module provides immutable provenance objects that track:
- When data was captured
- Where it came from (source URL, HTTP method, status)
- Cryptographic hashes of payloads and artifacts
- Patient/encounter context hints

Attach Provenance to:
- Every extracted clinical field bundle
- Every downloaded artifact (PDFs, images, documents)
- Every AI-generated summary

This enables complete audit trail for regulatory compliance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import hashlib
import json


def sha256_bytes(b: bytes) -> str:
    """Compute SHA-256 hash of raw bytes."""
    return hashlib.sha256(b).hexdigest()


def sha256_json(obj: Any) -> str:
    """Compute SHA-256 hash of canonical JSON representation."""
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(data)


@dataclass(frozen=True)
class Provenance:
    """
    Medico-legal traceability object.

    Attach this to:
      - every extracted clinical field bundle
      - every downloaded artifact
    so you can always point back to the exact source event.

    Attributes:
        captured_at: ISO 8601 timestamp when data was captured
        source_url: The URL from which data was retrieved
        http_method: HTTP method used (GET, POST, etc.)
        status: HTTP status code returned
        payload_hash: SHA-256 hash over raw payload bytes (or canonical JSON)
        artifact_hash: SHA-256 hash over downloaded file bytes
        patient_hint: Optional patient identifier for context
        encounter_hint: Optional encounter identifier for context
        meta: Additional metadata dictionary
    """
    captured_at: str  # ISO 8601
    source_url: str
    http_method: str = "GET"
    status: Optional[int] = None

    payload_hash: Optional[str] = None
    artifact_hash: Optional[str] = None

    patient_hint: Optional[str] = None
    encounter_hint: Optional[str] = None

    meta: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def now(
        source_url: str,
        http_method: str = "GET",
        status: Optional[int] = None,
        **kwargs
    ) -> "Provenance":
        """
        Create a Provenance object with current timestamp.

        Args:
            source_url: The URL from which data was retrieved
            http_method: HTTP method used
            status: HTTP status code
            **kwargs: Additional fields (payload_hash, artifact_hash, patient_hint, etc.)

        Returns:
            Provenance object with current UTC timestamp
        """
        ts = datetime.now(timezone.utc).isoformat()
        return Provenance(
            captured_at=ts,
            source_url=source_url,
            http_method=http_method,
            status=status,
            **kwargs
        )

    @staticmethod
    def from_raw_event(raw_event: Dict[str, Any]) -> "Provenance":
        """
        Create Provenance from a raw event dictionary.

        Args:
            raw_event: Dictionary containing event data with keys like
                      'timestamp', 'endpoint', 'method', 'status', 'patient_id', 'payload'

        Returns:
            Provenance object derived from the raw event
        """
        payload = raw_event.get("payload")
        payload_hash = None
        if payload:
            if isinstance(payload, bytes):
                payload_hash = sha256_bytes(payload)
            else:
                payload_hash = sha256_json(payload)

        return Provenance(
            captured_at=raw_event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            source_url=raw_event.get("endpoint", "unknown"),
            http_method=raw_event.get("method", "GET"),
            status=raw_event.get("status"),
            payload_hash=payload_hash,
            patient_hint=raw_event.get("patient_id"),
            meta={"source": raw_event.get("source", "unknown")}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "captured_at": self.captured_at,
            "source_url": self.source_url,
            "http_method": self.http_method,
            "status": self.status,
            "payload_hash": self.payload_hash,
            "artifact_hash": self.artifact_hash,
            "patient_hint": self.patient_hint,
            "encounter_hint": self.encounter_hint,
            "meta": self.meta,
        }

    def with_artifact_hash(self, artifact_bytes: bytes) -> "Provenance":
        """
        Create a new Provenance with the artifact hash set.

        Args:
            artifact_bytes: The raw bytes of the artifact

        Returns:
            New Provenance object with artifact_hash populated
        """
        return Provenance(
            captured_at=self.captured_at,
            source_url=self.source_url,
            http_method=self.http_method,
            status=self.status,
            payload_hash=self.payload_hash,
            artifact_hash=sha256_bytes(artifact_bytes),
            patient_hint=self.patient_hint,
            encounter_hint=self.encounter_hint,
            meta=self.meta,
        )


@dataclass(frozen=True)
class ProvenanceChain:
    """
    Chain of provenance for derived data.

    Use this when data goes through multiple transformations:
    Raw Event -> Indexed Event -> Interpreted Record -> AI Summary

    Each step adds its own provenance while preserving the chain.
    """
    chain: tuple  # Tuple of Provenance objects, oldest first

    @staticmethod
    def start(provenance: Provenance) -> "ProvenanceChain":
        """Start a new provenance chain."""
        return ProvenanceChain(chain=(provenance,))

    def extend(self, provenance: Provenance) -> "ProvenanceChain":
        """Add a new provenance to the chain."""
        return ProvenanceChain(chain=self.chain + (provenance,))

    @property
    def origin(self) -> Provenance:
        """Get the original provenance (first in chain)."""
        return self.chain[0]

    @property
    def latest(self) -> Provenance:
        """Get the most recent provenance (last in chain)."""
        return self.chain[-1]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chain": [p.to_dict() for p in self.chain],
            "origin": self.origin.to_dict(),
            "latest": self.latest.to_dict(),
        }
