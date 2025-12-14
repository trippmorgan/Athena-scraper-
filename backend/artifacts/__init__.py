"""
Artifacts Module: Document Reference Tracking and Missing Detection

This module provides:
- DocumentRef: Reference to clinical documents from Athena payloads
- MissingArtifactDetector: Identifies documents that need to be downloaded
- ArtifactIndex: Protocol for checking document existence

Use this to:
1. Extract document references from intercepted Athena payloads
2. Check which documents are already in the artifact store
3. Queue missing documents for download
"""

from .missing_detector import (
    DocumentRef,
    MissingDocument,
    ArtifactIndex,
    MissingArtifactDetector,
    InMemoryArtifactIndex,
    extract_document_refs,
    get_artifact_detector,
    get_artifact_index,
)

__all__ = [
    "DocumentRef",
    "MissingDocument",
    "ArtifactIndex",
    "MissingArtifactDetector",
    "InMemoryArtifactIndex",
    "extract_document_refs",
    "get_artifact_detector",
    "get_artifact_index",
]
