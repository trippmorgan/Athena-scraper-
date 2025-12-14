"""
Event Indexer: Layer 2 of the Shadow EHR Architecture

==============================================================================
ARCHITECTURAL CONTEXT
==============================================================================

This module implements the Event Indexer - a critical intermediary layer between
raw event capture (Layer 1) and clinical interpretation (Layer 3).

The Problem It Solves:
----------------------
"Premature interpretation" occurs when we try to extract clinical meaning from
unstable, poorly-understood data structures. This leads to:
  - Fragile extraction logic that breaks with minor API changes
  - Lost data when extraction fails silently
  - Inability to reprocess historical data with improved interpreters

The Solution:
-------------
The Event Indexer provides a STABLE classification layer that:
  1. Categorizes events by clinical domain WITHOUT extracting clinical content
  2. Maintains immutable pointers to raw events for provenance
  3. Enables retrospective reprocessing as interpreters improve
  4. Tracks confidence levels and extraction quality metrics

Data Flow:
----------
    [Athena API] → [Raw Event Store] → [Event Indexer] → [Clinical Interpreters]
                         ↑                    ↓
                    Layer 1              Layer 2
                  (immutable)         (reprocessable)

Index Entry Structure:
----------------------
Each index entry contains:
  - event_id: Pointer to raw event (immutable reference)
  - timestamp: When the original event occurred
  - patient_id: Clinical subject identifier
  - category: High-level clinical domain (medication, problem, vital, etc.)
  - subcategory: More specific classification within domain
  - source_type: Origin of the data (passive_intercept, active_fetch, etc.)
  - confidence: Classification confidence score (0.0-1.0)
  - extraction_hints: Metadata to guide downstream interpreters
  - indexer_version: Version of indexer that created this entry

==============================================================================
CLINICAL CATEGORY TAXONOMY
==============================================================================

Primary Categories (aligned with FHIR resource types):
------------------------------------------------------
  MEDICATION    - Drug orders, prescriptions, medication events
  PROBLEM       - Diagnoses, conditions, clinical problems
  VITAL         - Vital signs, measurements, observations
  LAB           - Laboratory results, pathology
  ALLERGY       - Allergies, adverse reactions, intolerances
  IMAGING       - Radiology, diagnostic imaging
  PROCEDURE     - Surgical procedures, clinical interventions
  ENCOUNTER     - Visits, admissions, clinical sessions
  DOCUMENT      - Clinical notes, reports, documents
  DEMOGRAPHIC   - Patient demographics, identifiers
  UNKNOWN       - Unclassified (requires manual review)

Subcategories (examples):
-------------------------
  MEDICATION.active      - Currently prescribed medications
  MEDICATION.historical  - Past medications
  MEDICATION.order       - New prescription orders
  PROBLEM.active         - Current diagnoses
  PROBLEM.historical     - Resolved conditions
  VITAL.encounter        - Vitals from a specific visit
  LAB.result             - Completed lab results
  LAB.order              - Pending lab orders

==============================================================================
"""

import re
import json
import hashlib
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("shadow-ehr")

# Current indexer version - increment when classification logic changes
INDEXER_VERSION = "2.0.0"


class ClinicalCategory(Enum):
    """
    Primary clinical categories aligned with FHIR resource types.

    These categories represent the fundamental clinical domains that
    downstream interpreters will process. The taxonomy is intentionally
    broad to maximize classification accuracy.
    """
    MEDICATION = "medication"
    PROBLEM = "problem"
    VITAL = "vital"
    LAB = "lab"
    ALLERGY = "allergy"
    IMAGING = "imaging"
    PROCEDURE = "procedure"
    ENCOUNTER = "encounter"
    DOCUMENT = "document"
    DEMOGRAPHIC = "demographic"
    COMPOUND = "compound"  # Multi-category payload (e.g., active fetch results)
    UNKNOWN = "unknown"


class SourceType(Enum):
    """
    Classification of how the event was captured.

    Understanding the source helps interpreters handle structural
    differences between passive intercepts and active fetches.
    """
    PASSIVE_INTERCEPT = "passive_intercept"  # XHR/fetch hook captured naturally
    ACTIVE_FETCH = "active_fetch"            # Deliberately triggered by extension
    MANUAL_UPLOAD = "manual_upload"          # User-uploaded data
    REPLAY = "replay"                        # Reprocessed from raw store
    UNKNOWN = "unknown"


@dataclass
class ExtractionHints:
    """
    Metadata to guide downstream clinical interpreters.

    These hints capture structural information about the payload
    WITHOUT extracting clinical content. Interpreters use these
    to select appropriate extraction strategies.
    """
    # Athena-specific structural markers
    has_events_array: bool = False           # Payload contains Events[] structure
    has_instance_nesting: bool = False       # Events contain Instance objects
    has_athena_class_markers: bool = False   # Contains __CLASS__ keys

    # Data availability indicators
    has_snomed_codes: bool = False           # SNOMED coding present
    has_icd10_codes: bool = False            # ICD-10 coding present
    has_rxnorm_codes: bool = False           # RxNorm drug codes present

    # Payload characteristics
    array_count: int = 0                     # Number of items in primary array
    nested_depth: int = 0                    # Maximum nesting depth observed
    key_signature: str = ""                  # Hash of top-level keys for pattern matching

    # Quality indicators
    has_required_fields: bool = False        # Contains minimum expected fields
    extraction_complexity: str = "unknown"   # simple, moderate, complex


@dataclass
class IndexEntry:
    """
    Lightweight index entry pointing to a raw event.

    This structure is optimized for:
      - Fast querying by patient, category, and time range
      - Minimal storage footprint (no clinical content duplication)
      - Immutable reference to source data for reproducibility
    """
    # Core identifiers
    id: str                                  # Unique index entry ID
    event_id: str                            # Pointer to raw event (IMMUTABLE)
    timestamp: str                           # ISO-8601 event timestamp

    # Classification
    patient_id: Optional[str]                # Clinical subject identifier
    category: str                            # Primary clinical category
    subcategory: Optional[str] = None        # Specific classification

    # Source tracking
    source_type: str = "unknown"             # How event was captured
    endpoint_pattern: str = ""               # Normalized URL pattern

    # Quality metrics
    confidence: float = 1.0                  # Classification confidence (0-1)
    extraction_hints: Dict = field(default_factory=dict)

    # Provenance
    indexer_version: str = INDEXER_VERSION
    indexed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class EventIndexer:
    """
    Event classification and indexing engine.

    This class provides both real-time indexing (as events arrive) and
    batch reprocessing (for historical data). It maintains a secondary
    index store that references the primary raw event store.

    Usage:
    ------
    # Real-time indexing
    indexer = EventIndexer(Path("data"))
    entry = await indexer.index_event(raw_event)

    # Batch reprocessing
    await indexer.reindex_all(force=True)

    # Query index
    entries = indexer.query(patient_id="12345", category="medication")
    """

    def __init__(self, data_dir: Path):
        """
        Initialize the Event Indexer.

        Args:
            data_dir: Directory containing raw_events.jsonl and where
                     event_index.jsonl will be stored
        """
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "event_index.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Classification patterns compiled once for performance
        self._compile_patterns()

        logger.info(f"[INDEXER] Initialized v{INDEXER_VERSION} at {self.data_dir}")

    def _compile_patterns(self):
        """
        Compile URL and payload patterns for classification.

        These patterns are derived from empirical analysis of Athena traffic
        (see docs/ATHENA_SCHEMA_ANALYSIS.md).
        """
        # URL patterns for category detection (order matters - more specific first)
        self.url_patterns = [
            # Active fetch synthetic URLs
            (r'active-fetch/FETCH_PREOP', ClinicalCategory.COMPOUND, 'preop'),
            (r'active-fetch/FETCH_ALL', ClinicalCategory.COMPOUND, 'all'),
            (r'active-fetch/FETCH_CURRENT', ClinicalCategory.COMPOUND, 'current'),
            (r'active-fetch/', ClinicalCategory.COMPOUND, None),

            # Athena sources parameter patterns (most common)
            (r'sources=active_medications', ClinicalCategory.MEDICATION, 'active'),
            (r'sources=medications', ClinicalCategory.MEDICATION, None),
            (r'sources=active_problems', ClinicalCategory.PROBLEM, 'active'),
            (r'sources=historical_problems', ClinicalCategory.PROBLEM, 'historical'),
            (r'sources=chart_overview_problems', ClinicalCategory.PROBLEM, 'overview'),
            (r'sources=allergies', ClinicalCategory.ALLERGY, None),
            (r'sources=measurements', ClinicalCategory.VITAL, None),
            (r'sources=vitals', ClinicalCategory.VITAL, None),
            (r'sources=demographics', ClinicalCategory.DEMOGRAPHIC, None),
            (r'sources=lab', ClinicalCategory.LAB, None),
            (r'sources=results', ClinicalCategory.LAB, 'result'),
            (r'sources=.*document', ClinicalCategory.DOCUMENT, None),

            # Athena multi-source compound requests (encounter sections)
            (r'encounter_sections', ClinicalCategory.ENCOUNTER, 'sections'),
            (r'encounter_id.*sources', ClinicalCategory.ENCOUNTER, 'data'),

            # Athena specific endpoints we've seen (from analysis)
            (r'security_label', ClinicalCategory.DEMOGRAPHIC, 'security'),
            (r'dashboard_default', ClinicalCategory.ENCOUNTER, 'dashboard'),
            (r'appointment_id', ClinicalCategory.ENCOUNTER, 'appointment'),
            (r'PATIENTIDS', ClinicalCategory.DEMOGRAPHIC, 'search'),
            (r'snomed_code', ClinicalCategory.PROBLEM, 'snomed_lookup'),

            # Standard path patterns
            (r'/medication', ClinicalCategory.MEDICATION, None),
            (r'/prescription', ClinicalCategory.MEDICATION, 'prescription'),
            (r'/problem', ClinicalCategory.PROBLEM, None),
            (r'/diagnosis', ClinicalCategory.PROBLEM, 'diagnosis'),
            (r'/condition', ClinicalCategory.PROBLEM, None),
            (r'/vital', ClinicalCategory.VITAL, None),
            (r'/measurement', ClinicalCategory.VITAL, None),
            (r'/lab', ClinicalCategory.LAB, None),
            (r'/result', ClinicalCategory.LAB, 'result'),
            (r'/allerg', ClinicalCategory.ALLERGY, None),
            (r'/imaging', ClinicalCategory.IMAGING, None),
            (r'/radiology', ClinicalCategory.IMAGING, 'radiology'),
            (r'/procedure', ClinicalCategory.PROCEDURE, None),
            (r'/surgery', ClinicalCategory.PROCEDURE, 'surgery'),
            (r'/encounter', ClinicalCategory.ENCOUNTER, None),
            (r'/visit', ClinicalCategory.ENCOUNTER, 'visit'),
            (r'/document', ClinicalCategory.DOCUMENT, None),
            (r'/note', ClinicalCategory.DOCUMENT, 'note'),
            (r'/patient', ClinicalCategory.DEMOGRAPHIC, None),
            (r'/demographic', ClinicalCategory.DEMOGRAPHIC, None),
        ]

        # Payload key patterns for fallback classification
        self.payload_patterns = {
            ClinicalCategory.MEDICATION: [
                'medications', 'active_medications', 'Medications',
                'prescriptions', 'drugs', 'rxnorm'
            ],
            ClinicalCategory.PROBLEM: [
                'problems', 'active_problems', 'Problems',
                'diagnoses', 'conditions', 'icd10'
            ],
            ClinicalCategory.VITAL: [
                'vitals', 'measurements', 'Vitals',
                'bloodPressure', 'heartRate', 'temperature'
            ],
            ClinicalCategory.LAB: [
                'labs', 'labResults', 'results',
                'panels', 'specimens'
            ],
            ClinicalCategory.ALLERGY: [
                'allergies', 'Allergies', 'allergyList',
                'adverseReactions', 'intolerances'
            ],
            ClinicalCategory.DEMOGRAPHIC: [
                'demographics', 'patient', 'firstName', 'lastName',
                'dateOfBirth', 'mrn'
            ],
        }

    def classify_event(self, endpoint: str, payload: Any) -> Tuple[ClinicalCategory, Optional[str], float]:
        """
        Classify an event into a clinical category.

        Classification Strategy (in order of precedence):
        1. URL pattern matching (highest confidence)
        2. Payload key inspection (moderate confidence)
        3. Payload structure analysis (lower confidence)
        4. Default to UNKNOWN (requires manual review)

        Args:
            endpoint: The API endpoint URL
            payload: The response payload (dict, list, or other)

        Returns:
            Tuple of (category, subcategory, confidence)
        """
        endpoint_lower = endpoint.lower()

        # Strategy 1: URL pattern matching
        for pattern, category, subcategory in self.url_patterns:
            if re.search(pattern, endpoint_lower, re.IGNORECASE):
                logger.debug(f"[INDEXER] Classified by URL: {category.value}/{subcategory}")
                return category, subcategory, 0.95

        # Strategy 2: Payload key inspection
        if isinstance(payload, dict):
            payload_keys = set(k.lower() for k in payload.keys())

            for category, marker_keys in self.payload_patterns.items():
                marker_set = set(k.lower() for k in marker_keys)
                if payload_keys & marker_set:
                    matched = payload_keys & marker_set
                    logger.debug(f"[INDEXER] Classified by payload keys: {category.value} (matched: {matched})")
                    return category, None, 0.75

            # Check for compound payload (multiple clinical domains)
            compound_keys = {'medications', 'problems', 'vitals', 'allergies', 'labs'}
            if len(payload_keys & compound_keys) >= 2:
                logger.debug(f"[INDEXER] Classified as COMPOUND (multiple domains)")
                return ClinicalCategory.COMPOUND, 'multi', 0.85

        # Strategy 3: Payload structure analysis (Athena-specific)
        if isinstance(payload, dict):
            # Check for Athena class markers
            if any('__CLASS__' in str(v) for v in payload.values() if isinstance(v, (dict, list, str))):
                # Try to infer from class name
                class_str = str(payload)
                if 'Medication' in class_str:
                    return ClinicalCategory.MEDICATION, None, 0.6
                if 'Problem' in class_str:
                    return ClinicalCategory.PROBLEM, None, 0.6

        logger.debug(f"[INDEXER] Unable to classify: {endpoint[:60]}")
        return ClinicalCategory.UNKNOWN, None, 0.0

    def detect_source_type(self, endpoint: str, payload: Any) -> SourceType:
        """
        Determine how the event was captured.

        Args:
            endpoint: The API endpoint URL
            payload: The response payload

        Returns:
            SourceType enum value
        """
        endpoint_lower = endpoint.lower()

        if 'active-fetch' in endpoint_lower:
            return SourceType.ACTIVE_FETCH

        if isinstance(payload, dict):
            if payload.get('_meta', {}).get('source') == 'active-fetch':
                return SourceType.ACTIVE_FETCH
            if payload.get('source') == 'replay':
                return SourceType.REPLAY

        return SourceType.PASSIVE_INTERCEPT

    def analyze_payload_structure(self, payload: Any) -> ExtractionHints:
        """
        Analyze payload structure to generate extraction hints.

        These hints guide downstream interpreters without extracting
        clinical content. Think of this as "metadata about the shape
        of the data" rather than "the data itself."

        Args:
            payload: The response payload to analyze

        Returns:
            ExtractionHints dataclass with structural metadata
        """
        hints = ExtractionHints()

        if not isinstance(payload, dict):
            return hints

        # Check for Athena-specific structures
        def check_nested(obj, depth=0, max_depth=5):
            """Recursively analyze structure."""
            if depth > max_depth or not isinstance(obj, (dict, list)):
                return depth

            max_found = depth

            if isinstance(obj, dict):
                # Check for Athena markers
                if '__CLASS__' in obj:
                    hints.has_athena_class_markers = True
                if 'Events' in obj:
                    hints.has_events_array = True
                if 'Instance' in obj:
                    hints.has_instance_nesting = True

                # Check for coding systems
                keys_str = ' '.join(obj.keys()).lower()
                if 'snomed' in keys_str:
                    hints.has_snomed_codes = True
                if 'icd10' in keys_str or 'icd-10' in keys_str:
                    hints.has_icd10_codes = True
                if 'rxnorm' in keys_str or 'ndc' in keys_str:
                    hints.has_rxnorm_codes = True

                for v in obj.values():
                    d = check_nested(v, depth + 1, max_depth)
                    max_found = max(max_found, d)

            elif isinstance(obj, list):
                hints.array_count = max(hints.array_count, len(obj))
                for item in obj[:10]:  # Sample first 10 items
                    d = check_nested(item, depth + 1, max_depth)
                    max_found = max(max_found, d)

            return max_found

        hints.nested_depth = check_nested(payload)

        # Generate key signature for pattern matching
        top_keys = sorted(payload.keys())[:10]
        hints.key_signature = hashlib.md5(
            '|'.join(top_keys).encode()
        ).hexdigest()[:8]

        # Assess extraction complexity
        if hints.nested_depth <= 2 and not hints.has_events_array:
            hints.extraction_complexity = "simple"
        elif hints.nested_depth <= 4 and hints.has_instance_nesting:
            hints.extraction_complexity = "moderate"
        else:
            hints.extraction_complexity = "complex"

        return hints

    def extract_patient_id(self, endpoint: str, payload: Any) -> Optional[str]:
        """
        Extract patient identifier from event.

        Tries multiple extraction strategies in order of reliability.

        Args:
            endpoint: The API endpoint URL
            payload: The response payload

        Returns:
            Patient ID string or None if not found
        """
        # Strategy 1: Payload metadata (most reliable for active fetch)
        if isinstance(payload, dict):
            if payload.get('patientId'):
                return str(payload['patientId'])
            if payload.get('_meta', {}).get('chartId'):
                return str(payload['_meta']['chartId'])
            if payload.get('patient_id'):
                return str(payload['patient_id'])

        # Strategy 2: URL patterns
        patterns = [
            r'chartid[=:](\d+)',
            r'patient[_-]?id[=:](\d+)',
            r'/chart/(\d+)',
            r'/patient/(\d+)',
            r'/(\d{6,})(?:/|$|\?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, endpoint, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def normalize_endpoint(self, endpoint: str) -> str:
        """
        Normalize endpoint URL for pattern matching.

        Replaces variable segments (IDs, timestamps) with placeholders
        to enable pattern-based analysis.

        Args:
            endpoint: Raw endpoint URL

        Returns:
            Normalized pattern string
        """
        normalized = endpoint

        # Replace numeric IDs with {id}
        normalized = re.sub(r'/\d{5,}(?=/|$|\?)', '/{id}', normalized)

        # Replace UUIDs with {uuid}
        normalized = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '{uuid}',
            normalized,
            flags=re.IGNORECASE
        )

        # Simplify query parameters (keep keys, remove values)
        if '?' in normalized:
            base, query = normalized.split('?', 1)
            params = re.findall(r'([a-zA-Z_]+)=', query)
            if params:
                normalized = f"{base}?{'+'.join(sorted(set(params)))}"

        return normalized[:200]  # Truncate for storage

    async def index_event(self, raw_event: Dict[str, Any]) -> IndexEntry:
        """
        Index a single raw event.

        This is the primary entry point for real-time indexing as events
        arrive from the Chrome extension.

        Args:
            raw_event: Raw event from the event store, containing:
                      - id: Event ID
                      - endpoint: API URL
                      - payload: Response data
                      - timestamp: ISO-8601 timestamp
                      - patient_id: Optional patient identifier

        Returns:
            IndexEntry that has been persisted to the index store
        """
        event_id = raw_event.get('id', '')
        endpoint = raw_event.get('endpoint', '')
        payload = raw_event.get('payload')
        timestamp = raw_event.get('timestamp', datetime.utcnow().isoformat())

        # Classify the event
        category, subcategory, confidence = self.classify_event(endpoint, payload)

        # Detect source type
        source_type = self.detect_source_type(endpoint, payload)

        # Extract patient ID
        patient_id = raw_event.get('patient_id') or self.extract_patient_id(endpoint, payload)

        # Analyze payload structure
        hints = self.analyze_payload_structure(payload)

        # Normalize endpoint for pattern matching
        endpoint_pattern = self.normalize_endpoint(endpoint)

        # Generate unique index entry ID
        entry_id = hashlib.md5(
            f"{event_id}:{INDEXER_VERSION}".encode()
        ).hexdigest()[:12]

        # Create index entry
        entry = IndexEntry(
            id=entry_id,
            event_id=event_id,
            timestamp=timestamp,
            patient_id=patient_id,
            category=category.value,
            subcategory=subcategory,
            source_type=source_type.value,
            endpoint_pattern=endpoint_pattern,
            confidence=confidence,
            extraction_hints=asdict(hints),
            indexer_version=INDEXER_VERSION,
        )

        # Persist to index store
        await self._append_index_entry(entry)

        logger.info(
            f"[INDEXER] Indexed: {category.value}/{subcategory or '-'} "
            f"(conf={confidence:.2f}, patient={patient_id or 'unknown'})"
        )

        return entry

    async def _append_index_entry(self, entry: IndexEntry):
        """Append entry to JSONL index file."""
        with self.index_path.open('a') as f:
            f.write(json.dumps(entry.to_dict()) + '\n')

    def query(
        self,
        patient_id: Optional[str] = None,
        category: Optional[str] = None,
        source_type: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query the index store.

        Args:
            patient_id: Filter by patient
            category: Filter by clinical category
            source_type: Filter by source type
            min_confidence: Minimum classification confidence
            limit: Maximum entries to return

        Returns:
            List of matching index entries (most recent first)
        """
        if not self.index_path.exists():
            return []

        results = []

        with self.index_path.open() as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Apply filters
                    if patient_id and entry.get('patient_id') != patient_id:
                        continue
                    if category and entry.get('category') != category:
                        continue
                    if source_type and entry.get('source_type') != source_type:
                        continue
                    if entry.get('confidence', 0) < min_confidence:
                        continue

                    results.append(entry)

                except json.JSONDecodeError:
                    continue

        # Return most recent first, limited
        return results[-limit:][::-1]

    def get_category_stats(self) -> Dict[str, int]:
        """
        Get count of entries by category.

        Returns:
            Dict mapping category name to count
        """
        stats = {}

        if not self.index_path.exists():
            return stats

        with self.index_path.open() as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    cat = entry.get('category', 'unknown')
                    stats[cat] = stats.get(cat, 0) + 1
                except json.JSONDecodeError:
                    continue

        return dict(sorted(stats.items(), key=lambda x: -x[1]))

    async def reindex_all(self, raw_events_path: Path, force: bool = False) -> Dict:
        """
        Reindex all raw events (batch reprocessing).

        This enables retrospective analysis when classification logic
        improves. Use force=True to reindex events that already have
        entries from the current indexer version.

        Args:
            raw_events_path: Path to raw_events.jsonl
            force: If True, reindex even if already indexed with current version

        Returns:
            Statistics about the reindexing operation
        """
        stats = {
            'total_events': 0,
            'indexed': 0,
            'skipped': 0,
            'errors': 0,
            'by_category': {}
        }

        if not raw_events_path.exists():
            logger.warning(f"[INDEXER] Raw events file not found: {raw_events_path}")
            return stats

        # Load existing index entries to avoid duplicates
        existing_ids = set()
        if not force and self.index_path.exists():
            with self.index_path.open() as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get('indexer_version') == INDEXER_VERSION:
                            existing_ids.add(entry.get('event_id'))
                    except json.JSONDecodeError:
                        continue

        logger.info(f"[INDEXER] Starting reindex (force={force}, existing={len(existing_ids)})")

        with raw_events_path.open() as f:
            for line in f:
                stats['total_events'] += 1

                try:
                    raw_event = json.loads(line)
                    event_id = raw_event.get('id')

                    if not force and event_id in existing_ids:
                        stats['skipped'] += 1
                        continue

                    entry = await self.index_event(raw_event)
                    stats['indexed'] += 1

                    cat = entry.category
                    stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1

                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"[INDEXER] Error indexing event: {e}")

        logger.info(
            f"[INDEXER] Reindex complete: {stats['indexed']} indexed, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        return stats


# ==============================================================================
# CONVENIENCE FUNCTIONS FOR INTEGRATION
# ==============================================================================

def create_indexer(data_dir: str = "data") -> EventIndexer:
    """
    Factory function to create an EventIndexer instance.

    Args:
        data_dir: Path to data directory

    Returns:
        Configured EventIndexer instance
    """
    return EventIndexer(Path(data_dir))


async def index_incoming_event(
    indexer: EventIndexer,
    endpoint: str,
    payload: Any,
    event_id: str,
    timestamp: Optional[str] = None,
    patient_id: Optional[str] = None
) -> IndexEntry:
    """
    Convenience function for indexing a newly captured event.

    Args:
        indexer: EventIndexer instance
        endpoint: API endpoint URL
        payload: Response payload
        event_id: Raw event ID from event store
        timestamp: Event timestamp (defaults to now)
        patient_id: Known patient ID (optional)

    Returns:
        Created IndexEntry
    """
    raw_event = {
        'id': event_id,
        'endpoint': endpoint,
        'payload': payload,
        'timestamp': timestamp or datetime.utcnow().isoformat(),
        'patient_id': patient_id,
    }

    return await indexer.index_event(raw_event)
