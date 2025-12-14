"""
Missing Artifact Detector: Identify Documents That Need Downloading

This module analyzes intercepted Athena payloads to find document references,
then checks which documents are missing from the artifact store.

Workflow:
1. Extract DocumentRefs from Athena JSON payloads
2. Check each ref against the ArtifactIndex
3. Return list of MissingDocuments that need downloading
4. Pass missing docs to DownloadManager

Document Types Detected:
- Clinical notes (op notes, H&Ps, progress notes)
- Lab results PDFs
- Imaging reports
- Scanned documents
- Consent forms
- Discharge summaries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol, Dict, Any, Set
import logging
import re

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentRef:
    """
    A reference to a document that should exist (extracted from Athena JSON payloads).

    Attributes:
        doc_id: Unique identifier for this document
        download_url: URL to download the document (may be None if not available)
        filename_hint: Suggested filename for storage
        doc_type: Type of document (note, lab, imaging, etc.)
        patient_id: Associated patient ID if known
        encounter_id: Associated encounter ID if known
        title: Document title if available
        created_date: Document creation date if available
    """
    doc_id: str
    download_url: Optional[str]
    filename_hint: str
    doc_type: Optional[str] = None
    patient_id: Optional[str] = None
    encounter_id: Optional[str] = None
    title: Optional[str] = None
    created_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "doc_id": self.doc_id,
            "download_url": self.download_url,
            "filename_hint": self.filename_hint,
            "doc_type": self.doc_type,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "title": self.title,
            "created_date": self.created_date,
        }


@dataclass(frozen=True)
class MissingDocument:
    """
    A document that needs to be downloaded.

    Attributes:
        ref: The DocumentRef for the missing document
        reason: Why the document is considered missing
    """
    ref: DocumentRef
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ref": self.ref.to_dict(),
            "reason": self.reason,
        }


class ArtifactIndex(Protocol):
    """
    Protocol for checking whether documents exist in storage.

    Implement this with your database/storage backend to check
    if a document has already been downloaded.
    """

    def has_doc(self, doc_id: str) -> bool:
        """Check if a document with the given ID exists in storage."""
        ...


class InMemoryArtifactIndex:
    """
    Simple in-memory artifact index for development/testing.

    In production, replace with database-backed implementation.
    """

    def __init__(self):
        self._docs: Set[str] = set()

    def has_doc(self, doc_id: str) -> bool:
        """Check if document exists."""
        return doc_id in self._docs

    def add_doc(self, doc_id: str) -> None:
        """Mark document as existing."""
        self._docs.add(doc_id)

    def remove_doc(self, doc_id: str) -> None:
        """Remove document from index."""
        self._docs.discard(doc_id)

    def count(self) -> int:
        """Get count of indexed documents."""
        return len(self._docs)


class MissingArtifactDetector:
    """
    Detects documents that are referenced in Athena payloads but not yet downloaded.

    Usage:
        index = InMemoryArtifactIndex()  # or database-backed
        detector = MissingArtifactDetector(index)

        # Extract refs from Athena payload
        refs = extract_document_refs(payload)

        # Find missing
        missing = detector.find_missing(refs)

        # Download missing
        for m in missing:
            if m.ref.download_url:
                download_manager.download(url=m.ref.download_url, ...)
    """

    def __init__(self, index: ArtifactIndex):
        """
        Initialize detector.

        Args:
            index: ArtifactIndex implementation for checking document existence
        """
        self.index = index

    def find_missing(self, refs: Iterable[DocumentRef]) -> List[MissingDocument]:
        """
        Find documents that are missing from storage.

        Args:
            refs: Iterable of DocumentRef objects to check

        Returns:
            List of MissingDocument objects for documents not in storage
        """
        missing: List[MissingDocument] = []

        for ref in refs:
            # Check if already downloaded
            if self.index.has_doc(ref.doc_id):
                continue

            # Check if downloadable
            if not ref.download_url:
                missing.append(MissingDocument(ref=ref, reason="no_download_url"))
                continue

            missing.append(MissingDocument(ref=ref, reason="not_in_store"))

        logger.info(f"[DETECTOR] Found {len(missing)} missing documents")
        return missing

    def find_downloadable(self, refs: Iterable[DocumentRef]) -> List[DocumentRef]:
        """
        Find documents that are missing AND have download URLs.

        Args:
            refs: Iterable of DocumentRef objects to check

        Returns:
            List of DocumentRef objects that can be downloaded
        """
        missing = self.find_missing(refs)
        return [m.ref for m in missing if m.reason == "not_in_store"]


def extract_document_refs(
    payload: Dict[str, Any],
    patient_id: Optional[str] = None,
    encounter_id: Optional[str] = None
) -> List[DocumentRef]:
    """
    Extract document references from an Athena JSON payload.

    This function handles various Athena payload formats to find
    document references that might need downloading.

    Args:
        payload: Raw Athena JSON payload
        patient_id: Optional patient ID for context
        encounter_id: Optional encounter ID for context

    Returns:
        List of DocumentRef objects found in the payload
    """
    refs: List[DocumentRef] = []

    # Pattern 1: Documents array
    documents = payload.get("Documents") or payload.get("documents") or []
    for doc in documents:
        if isinstance(doc, dict):
            ref = _extract_from_document_object(doc, patient_id, encounter_id)
            if ref:
                refs.append(ref)

    # Pattern 2: Events array with document instances
    events = payload.get("Events") or payload.get("events") or []
    for event in events:
        if isinstance(event, dict):
            instance = event.get("Instance") or event.get("instance") or {}
            if isinstance(instance, dict):
                ref = _extract_from_instance(instance, event, patient_id, encounter_id)
                if ref:
                    refs.append(ref)

    # Pattern 3: Attachments
    attachments = payload.get("Attachments") or payload.get("attachments") or []
    for att in attachments:
        if isinstance(att, dict):
            ref = _extract_from_attachment(att, patient_id, encounter_id)
            if ref:
                refs.append(ref)

    # Pattern 4: Results with document links
    results = payload.get("Results") or payload.get("results") or []
    for result in results:
        if isinstance(result, dict):
            ref = _extract_from_result(result, patient_id, encounter_id)
            if ref:
                refs.append(ref)

    # Pattern 5: Nested DocumentList
    doc_list = payload.get("DocumentList") or payload.get("documentList") or []
    for doc in doc_list:
        if isinstance(doc, dict):
            ref = _extract_from_document_object(doc, patient_id, encounter_id)
            if ref:
                refs.append(ref)

    # Deduplicate by doc_id
    seen: Set[str] = set()
    unique_refs: List[DocumentRef] = []
    for ref in refs:
        if ref.doc_id not in seen:
            seen.add(ref.doc_id)
            unique_refs.append(ref)

    logger.debug(f"[DETECTOR] Extracted {len(unique_refs)} document refs from payload")
    return unique_refs


def _extract_from_document_object(
    doc: Dict[str, Any],
    patient_id: Optional[str],
    encounter_id: Optional[str]
) -> Optional[DocumentRef]:
    """Extract DocumentRef from a document object."""
    doc_id = (
        doc.get("DocumentId") or
        doc.get("documentId") or
        doc.get("Id") or
        doc.get("id") or
        doc.get("DocumentID")
    )
    if not doc_id:
        return None

    download_url = (
        doc.get("DownloadUrl") or
        doc.get("downloadUrl") or
        doc.get("Url") or
        doc.get("url") or
        doc.get("FileUrl") or
        doc.get("fileUrl")
    )

    title = (
        doc.get("Title") or
        doc.get("title") or
        doc.get("DocumentTitle") or
        doc.get("Description") or
        doc.get("Name")
    )

    doc_type = (
        doc.get("DocumentType") or
        doc.get("documentType") or
        doc.get("Type") or
        doc.get("type") or
        doc.get("Category")
    )

    created = doc.get("CreatedDate") or doc.get("createdDate") or doc.get("Date")

    # Generate filename hint
    filename = _generate_filename(doc_id, title, doc_type)

    return DocumentRef(
        doc_id=str(doc_id),
        download_url=download_url,
        filename_hint=filename,
        doc_type=doc_type,
        patient_id=patient_id or doc.get("PatientId") or doc.get("patientId"),
        encounter_id=encounter_id or doc.get("EncounterId") or doc.get("encounterId"),
        title=title,
        created_date=created,
    )


def _extract_from_instance(
    instance: Dict[str, Any],
    event: Dict[str, Any],
    patient_id: Optional[str],
    encounter_id: Optional[str]
) -> Optional[DocumentRef]:
    """Extract DocumentRef from an event instance."""
    doc_id = (
        instance.get("DocumentId") or
        instance.get("Id") or
        event.get("Id") or
        event.get("EventId")
    )
    if not doc_id:
        return None

    # Check if this is actually a document (has download URL or document type)
    download_url = instance.get("DownloadUrl") or instance.get("FileUrl")
    doc_type = instance.get("DocumentType") or instance.get("Type")

    # Skip if not a document-like event
    if not download_url and not doc_type:
        return None

    title = instance.get("DisplayName") or instance.get("Title") or instance.get("Description")
    created = instance.get("CreatedDate") or instance.get("Date")
    filename = _generate_filename(doc_id, title, doc_type)

    return DocumentRef(
        doc_id=str(doc_id),
        download_url=download_url,
        filename_hint=filename,
        doc_type=doc_type,
        patient_id=patient_id,
        encounter_id=encounter_id,
        title=title,
        created_date=created,
    )


def _extract_from_attachment(
    att: Dict[str, Any],
    patient_id: Optional[str],
    encounter_id: Optional[str]
) -> Optional[DocumentRef]:
    """Extract DocumentRef from an attachment object."""
    att_id = att.get("AttachmentId") or att.get("Id") or att.get("id")
    if not att_id:
        return None

    download_url = (
        att.get("DownloadUrl") or
        att.get("Url") or
        att.get("FileUrl") or
        att.get("ContentUrl")
    )

    filename = att.get("Filename") or att.get("FileName") or att.get("Name")
    mime_type = att.get("MimeType") or att.get("ContentType")

    # Infer doc type from mime
    doc_type = None
    if mime_type:
        if "pdf" in mime_type.lower():
            doc_type = "pdf"
        elif "image" in mime_type.lower():
            doc_type = "image"

    return DocumentRef(
        doc_id=str(att_id),
        download_url=download_url,
        filename_hint=filename or f"attachment_{att_id}",
        doc_type=doc_type,
        patient_id=patient_id,
        encounter_id=encounter_id,
        title=att.get("Description") or filename,
        created_date=att.get("CreatedDate"),
    )


def _extract_from_result(
    result: Dict[str, Any],
    patient_id: Optional[str],
    encounter_id: Optional[str]
) -> Optional[DocumentRef]:
    """Extract DocumentRef from a result object (lab results, imaging, etc.)."""
    result_id = result.get("ResultId") or result.get("Id") or result.get("id")
    if not result_id:
        return None

    # Check for document/report URL
    download_url = (
        result.get("ReportUrl") or
        result.get("DocumentUrl") or
        result.get("PdfUrl") or
        result.get("DownloadUrl")
    )

    if not download_url:
        return None

    title = result.get("ResultName") or result.get("Name") or result.get("Description")
    doc_type = result.get("ResultType") or "result"
    filename = _generate_filename(result_id, title, doc_type)

    return DocumentRef(
        doc_id=str(result_id),
        download_url=download_url,
        filename_hint=filename,
        doc_type=doc_type,
        patient_id=patient_id,
        encounter_id=encounter_id,
        title=title,
        created_date=result.get("ResultDate") or result.get("Date"),
    )


def _generate_filename(
    doc_id: str,
    title: Optional[str],
    doc_type: Optional[str]
) -> str:
    """Generate a safe filename for a document."""
    parts = []

    # Add doc type prefix
    if doc_type:
        safe_type = re.sub(r'[^\w\-]', '_', doc_type.lower())[:20]
        parts.append(safe_type)

    # Add sanitized title
    if title:
        safe_title = re.sub(r'[^\w\-\s]', '', title)[:50].strip().replace(' ', '_')
        if safe_title:
            parts.append(safe_title)

    # Add doc ID
    parts.append(str(doc_id)[:20])

    # Default extension
    ext = ".pdf"
    if doc_type:
        doc_type_lower = doc_type.lower()
        if "image" in doc_type_lower or "jpg" in doc_type_lower or "png" in doc_type_lower:
            ext = ".jpg"
        elif "tiff" in doc_type_lower:
            ext = ".tiff"

    return "_".join(parts) + ext


# Global detector instance
_detector: Optional[MissingArtifactDetector] = None
_index: Optional[InMemoryArtifactIndex] = None


def get_artifact_detector() -> MissingArtifactDetector:
    """Get or create the global artifact detector instance."""
    global _detector, _index
    if _detector is None:
        _index = InMemoryArtifactIndex()
        _detector = MissingArtifactDetector(_index)
    return _detector


def get_artifact_index() -> InMemoryArtifactIndex:
    """Get or create the global artifact index instance."""
    global _index
    if _index is None:
        _index = InMemoryArtifactIndex()
    return _index
