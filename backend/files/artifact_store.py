"""
Artifact Store: Secure Storage for Downloaded Clinical Documents

This module provides abstract and concrete implementations for storing
downloaded clinical artifacts (PDFs, images, documents) with full provenance.

Storage backends:
- DiskArtifactStore: Local filesystem (development, single-server)
- (Future) S3ArtifactStore: AWS S3 for production
- (Future) PostgresArtifactStore: Postgres large objects

Each stored artifact includes:
- Unique artifact ID
- Original filename
- MIME type
- File size
- Complete provenance chain
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
import uuid
import json
import logging
import os

from provenance import Provenance

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredArtifact:
    """
    Represents a stored artifact with full provenance.

    Attributes:
        artifact_id: Unique identifier for this artifact
        path: Storage path (filesystem path, S3 key, etc.)
        size_bytes: Size of the artifact in bytes
        mime_type: MIME type of the artifact
        provenance: Provenance object with traceability data
        original_filename: Original filename if known
        stored_at: ISO 8601 timestamp when artifact was stored
    """
    artifact_id: str
    path: str
    size_bytes: int
    mime_type: Optional[str]
    provenance: Provenance
    original_filename: Optional[str] = None
    stored_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "provenance": self.provenance.to_dict(),
            "original_filename": self.original_filename,
            "stored_at": self.stored_at,
        }


class ArtifactStore(Protocol):
    """
    Abstract store interface.

    Implement this protocol to back artifact storage with:
    - Local disk
    - S3
    - Postgres large objects
    - Azure Blob Storage
    - etc.
    """

    def put(
        self,
        *,
        bytes_data: bytes,
        filename: str,
        mime_type: Optional[str],
        provenance: Provenance
    ) -> StoredArtifact:
        """Store an artifact and return the stored artifact record."""
        ...

    def get(self, artifact_id: str) -> Optional[bytes]:
        """Retrieve artifact bytes by ID."""
        ...

    def get_metadata(self, artifact_id: str) -> Optional[StoredArtifact]:
        """Retrieve artifact metadata by ID."""
        ...

    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact by ID."""
        ...

    def list_by_patient(self, patient_id: str) -> List[StoredArtifact]:
        """List all artifacts for a patient."""
        ...


class DiskArtifactStore:
    """
    Filesystem-based artifact store.

    Directory structure:
    root_dir/
        artifacts/
            {artifact_id}__{safe_filename}
        index/
            {artifact_id}.json  (metadata)
        by_patient/
            {patient_id}/
                {artifact_id}.json  (symlink or reference)
    """

    def __init__(self, root_dir: str):
        """
        Initialize disk artifact store.

        Args:
            root_dir: Root directory for artifact storage
        """
        self.root = Path(root_dir)
        self.artifacts_dir = self.root / "artifacts"
        self.index_dir = self.root / "index"
        self.by_patient_dir = self.root / "by_patient"

        # Create directories
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.by_patient_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[STORE] Initialized DiskArtifactStore at {self.root}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem storage."""
        # Remove path separators and null bytes
        safe = filename.replace("/", "_").replace("\\", "_").replace("\x00", "")
        # Limit length
        if len(safe) > 200:
            ext = Path(safe).suffix
            safe = safe[:200-len(ext)] + ext
        return safe or "artifact"

    def put(
        self,
        *,
        bytes_data: bytes,
        filename: str,
        mime_type: Optional[str],
        provenance: Provenance
    ) -> StoredArtifact:
        """
        Store an artifact on disk.

        Args:
            bytes_data: Raw bytes of the artifact
            filename: Original filename
            mime_type: MIME type of the artifact
            provenance: Provenance object for traceability

        Returns:
            StoredArtifact with storage details
        """
        artifact_id = str(uuid.uuid4())
        safe_filename = self._sanitize_filename(filename)
        stored_at = datetime.now(timezone.utc).isoformat()

        # Write artifact file
        artifact_path = self.artifacts_dir / f"{artifact_id}__{safe_filename}"
        artifact_path.write_bytes(bytes_data)

        # Create stored artifact record
        stored = StoredArtifact(
            artifact_id=artifact_id,
            path=str(artifact_path),
            size_bytes=len(bytes_data),
            mime_type=mime_type,
            provenance=provenance,
            original_filename=filename,
            stored_at=stored_at,
        )

        # Write index metadata
        index_path = self.index_dir / f"{artifact_id}.json"
        index_path.write_text(json.dumps(stored.to_dict(), indent=2))

        # Create patient index if patient_hint is present
        if provenance.patient_hint:
            patient_dir = self.by_patient_dir / provenance.patient_hint
            patient_dir.mkdir(parents=True, exist_ok=True)
            patient_index = patient_dir / f"{artifact_id}.json"
            patient_index.write_text(json.dumps({
                "artifact_id": artifact_id,
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": len(bytes_data),
                "stored_at": stored_at,
                "source_url": provenance.source_url,
            }, indent=2))

        logger.info(
            f"[STORE] Stored artifact: {artifact_id} "
            f"({len(bytes_data)} bytes, {mime_type})"
        )

        return stored

    def get(self, artifact_id: str) -> Optional[bytes]:
        """
        Retrieve artifact bytes by ID.

        Args:
            artifact_id: The artifact identifier

        Returns:
            Raw bytes of the artifact, or None if not found
        """
        # Find artifact file (need to handle the __ separator)
        for f in self.artifacts_dir.glob(f"{artifact_id}__*"):
            return f.read_bytes()

        logger.warning(f"[STORE] Artifact not found: {artifact_id}")
        return None

    def get_metadata(self, artifact_id: str) -> Optional[StoredArtifact]:
        """
        Retrieve artifact metadata by ID.

        Args:
            artifact_id: The artifact identifier

        Returns:
            StoredArtifact metadata, or None if not found
        """
        index_path = self.index_dir / f"{artifact_id}.json"
        if not index_path.exists():
            return None

        try:
            data = json.loads(index_path.read_text())
            return StoredArtifact(
                artifact_id=data["artifact_id"],
                path=data["path"],
                size_bytes=data["size_bytes"],
                mime_type=data.get("mime_type"),
                provenance=Provenance(**data["provenance"]),
                original_filename=data.get("original_filename"),
                stored_at=data.get("stored_at"),
            )
        except Exception as e:
            logger.error(f"[STORE] Error reading metadata: {e}")
            return None

    def delete(self, artifact_id: str) -> bool:
        """
        Delete an artifact by ID.

        Args:
            artifact_id: The artifact identifier

        Returns:
            True if deleted, False if not found
        """
        deleted = False

        # Delete artifact file
        for f in self.artifacts_dir.glob(f"{artifact_id}__*"):
            f.unlink()
            deleted = True

        # Delete index
        index_path = self.index_dir / f"{artifact_id}.json"
        if index_path.exists():
            index_path.unlink()
            deleted = True

        # Delete patient index entries
        for patient_dir in self.by_patient_dir.iterdir():
            if patient_dir.is_dir():
                patient_index = patient_dir / f"{artifact_id}.json"
                if patient_index.exists():
                    patient_index.unlink()

        if deleted:
            logger.info(f"[STORE] Deleted artifact: {artifact_id}")
        return deleted

    def list_by_patient(self, patient_id: str) -> List[StoredArtifact]:
        """
        List all artifacts for a patient.

        Args:
            patient_id: The patient identifier

        Returns:
            List of StoredArtifact objects
        """
        patient_dir = self.by_patient_dir / patient_id
        if not patient_dir.exists():
            return []

        artifacts = []
        for f in patient_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                artifact_id = data["artifact_id"]
                meta = self.get_metadata(artifact_id)
                if meta:
                    artifacts.append(meta)
            except Exception as e:
                logger.error(f"[STORE] Error reading patient index: {e}")

        return artifacts

    def list_all(self, limit: int = 100) -> List[StoredArtifact]:
        """
        List all artifacts (with limit).

        Args:
            limit: Maximum number of artifacts to return

        Returns:
            List of StoredArtifact objects
        """
        artifacts = []
        for f in sorted(self.index_dir.glob("*.json"))[:limit]:
            try:
                data = json.loads(f.read_text())
                artifacts.append(StoredArtifact(
                    artifact_id=data["artifact_id"],
                    path=data["path"],
                    size_bytes=data["size_bytes"],
                    mime_type=data.get("mime_type"),
                    provenance=Provenance(**data["provenance"]),
                    original_filename=data.get("original_filename"),
                    stored_at=data.get("stored_at"),
                ))
            except Exception as e:
                logger.error(f"[STORE] Error reading index: {e}")

        return artifacts

    def stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        artifact_count = len(list(self.index_dir.glob("*.json")))
        total_size = sum(f.stat().st_size for f in self.artifacts_dir.iterdir() if f.is_file())
        patient_count = len([d for d in self.by_patient_dir.iterdir() if d.is_dir()])

        return {
            "artifact_count": artifact_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "patient_count": patient_count,
            "storage_path": str(self.root),
        }


# Global store instance
_store: Optional[DiskArtifactStore] = None


def get_artifact_store(root_dir: str = "data/artifacts") -> DiskArtifactStore:
    """Get or create the global artifact store instance."""
    global _store
    if _store is None:
        _store = DiskArtifactStore(root_dir)
    return _store
