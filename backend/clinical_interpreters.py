"""
Clinical Interpreters: Layer 3 of the Shadow EHR Architecture

==============================================================================
ARCHITECTURAL CONTEXT
==============================================================================

This module implements Clinical Interpreters - specialized extractors that
transform raw EHR data into clinically meaningful, standardized structures.

The Problem It Solves:
----------------------
Raw EHR data (especially from Athena) is:
  - Deeply nested with proprietary structures
  - Inconsistently keyed (camelCase, PascalCase, snake_case mixed)
  - Coded with multiple systems (SNOMED, ICD-10, RxNorm, NDC)
  - Missing obvious fields (drug name buried 4 levels deep)

Clinical Interpreters provide:
  - Domain-specific extraction logic (medications, problems, vitals, etc.)
  - Versioned output schemas for reproducibility
  - Confidence scoring for extraction quality
  - Provenance tracking back to raw events

Data Flow:
----------
    [Event Index] → [Clinical Interpreters] → [Standardized Clinical Records]
         ↑                    ↓                          ↓
      Layer 2              Layer 3                 [Dashboard]
   (classification)    (interpretation)            Layer 4

==============================================================================
INTERPRETER DESIGN PRINCIPLES
==============================================================================

1. DEFENSIVE EXTRACTION
   - Never assume a field exists
   - Try multiple paths for each piece of data
   - Log what was found vs. expected

2. CLINICAL RELEVANCE
   - Extract what clinicians need, not everything available
   - For vascular surgery: antithrombotics, anticoagulants, vasodilators
   - For problems: focus on ICD-10 for billing/risk stratification

3. PROVENANCE
   - Every extracted record links back to source event
   - Track interpreter version that produced output
   - Enable re-interpretation when logic improves

4. CONFIDENCE SCORING
   - Rate extraction quality (0.0-1.0)
   - Low confidence = partial/uncertain extraction
   - High confidence = all expected fields found

==============================================================================
"""

import re
import json
import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Type
from enum import Enum

logger = logging.getLogger("shadow-ehr")

# ==============================================================================
# INTERPRETER VERSIONING
# ==============================================================================

INTERPRETER_VERSIONS = {
    "medication": "1.0.0",
    "problem": "1.0.0",
    "vital": "1.0.0",
    "allergy": "1.0.0",
}


# ==============================================================================
# STANDARDIZED OUTPUT SCHEMAS
# ==============================================================================

@dataclass
class ExtractedMedication:
    """
    Standardized medication record for clinical use.

    Designed for vascular surgery workflow:
    - Antithrombotic identification (clopidogrel, aspirin, warfarin)
    - Dosing verification
    - Therapeutic class for drug interaction checking
    """
    # Core identification
    id: str                                  # Unique record ID
    name: str                                # Drug name (generic preferred)
    brand_name: Optional[str] = None         # Brand name if available

    # Dosing
    dose: Optional[str] = None               # e.g., "75mg"
    frequency: Optional[str] = None          # e.g., "once daily"
    route: Optional[str] = None              # e.g., "oral", "IV"
    sig: Optional[str] = None                # Full sig text

    # Classification
    therapeutic_class: Optional[str] = None  # e.g., "ANTIPLATELET"
    is_antithrombotic: bool = False          # Critical for vascular surgery

    # Coding
    rxnorm_code: Optional[str] = None        # RxNorm CUI
    ndc_code: Optional[str] = None           # NDC code

    # Status
    status: str = "active"                   # active, stopped, on-hold

    # Provenance
    source_event_id: str = ""                # Link to raw event
    confidence: float = 1.0                  # Extraction confidence
    interpreter_version: str = ""            # Which interpreter version

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExtractedProblem:
    """
    Standardized problem/diagnosis record for clinical use.

    Designed for risk stratification:
    - ICD-10 codes for billing and analytics
    - SNOMED codes for clinical decision support
    - Vascular-relevant conditions flagged
    """
    # Core identification
    id: str                                  # Unique record ID
    display_name: str                        # Human-readable name

    # Coding (ICD-10 preferred for billing/analytics)
    icd10_code: Optional[str] = None         # e.g., "I70.213"
    icd10_description: Optional[str] = None  # Full ICD-10 description
    snomed_code: Optional[str] = None        # SNOMED CT code
    snomed_description: Optional[str] = None # SNOMED description

    # Classification
    is_vascular: bool = False                # Relevant to vascular surgery
    is_cardiovascular_risk: bool = False     # CV risk factor
    severity: Optional[str] = None           # mild, moderate, severe

    # Status
    clinical_status: str = "active"          # active, resolved, inactive
    is_primary: bool = False                 # Primary diagnosis flag

    # Temporal
    onset_date: Optional[str] = None         # When diagnosed

    # Provenance
    source_event_id: str = ""                # Link to raw event
    confidence: float = 1.0                  # Extraction confidence
    interpreter_version: str = ""            # Which interpreter version

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class InterpretationResult:
    """
    Container for interpretation results with metadata.
    """
    category: str                            # medication, problem, vital, etc.
    records: List[Dict]                      # Extracted records
    source_event_id: str                     # Raw event ID
    patient_id: Optional[str]                # Patient identifier
    interpreter_version: str                 # Interpreter version used
    interpreted_at: str                      # Timestamp
    confidence: float                        # Overall confidence
    warnings: List[str] = field(default_factory=list)  # Extraction warnings

    def to_dict(self) -> Dict:
        return asdict(self)


# ==============================================================================
# BASE INTERPRETER CLASS
# ==============================================================================

class ClinicalInterpreter(ABC):
    """
    Abstract base class for clinical interpreters.

    Each interpreter specializes in extracting one type of clinical data
    (medications, problems, vitals, etc.) from raw EHR payloads.
    """

    def __init__(self):
        self.version = "0.0.0"
        self.category = "unknown"
        self._extraction_warnings: List[str] = []

    @abstractmethod
    def can_interpret(self, index_entry: Dict) -> bool:
        """
        Determine if this interpreter can handle the given indexed event.

        Args:
            index_entry: Index entry from Layer 2 Event Indexer

        Returns:
            True if this interpreter should process the event
        """
        pass

    @abstractmethod
    def interpret(self, raw_event: Dict, index_entry: Dict) -> InterpretationResult:
        """
        Extract clinical data from a raw event.

        Args:
            raw_event: Raw event from Layer 1 Event Store
            index_entry: Index entry from Layer 2 with extraction hints

        Returns:
            InterpretationResult containing extracted records
        """
        pass

    def _warn(self, message: str):
        """Add an extraction warning."""
        self._extraction_warnings.append(message)
        logger.debug(f"[{self.category.upper()}] Warning: {message}")

    def _generate_id(self, data: Any) -> str:
        """Generate deterministic ID from data."""
        content = str(data).encode('utf-8')
        return hashlib.md5(content).hexdigest()[:12]


# ==============================================================================
# MEDICATION INTERPRETER
# ==============================================================================

class MedicationInterpreter(ClinicalInterpreter):
    """
    Extracts medication data from Athena payloads.

    ATHENA STRUCTURE (verified from traffic analysis):
    -------------------------------------------------
    active_medications.Medications[] = {
        Events[] = {
            Instance: {
                DisplayName: "clopidogrel 75mg"     ← DRUG NAME
                UnstructuredSig: "TAKE ONE..."      ← DOSING
                QuantityValue: 30
                Medication: {
                    TherapeuticClass: "ANTIPLATELET"
                    ProductName: "PLAVIX"
                }
            }
        }
    }

    VASCULAR SURGERY RELEVANCE:
    ---------------------------
    Flags medications critical for perioperative management:
    - Antiplatelets (clopidogrel, aspirin, ticagrelor)
    - Anticoagulants (warfarin, heparin, enoxaparin, rivaroxaban)
    - Vasodilators (cilostazol)
    """

    # Antithrombotic keywords for vascular surgery relevance
    ANTITHROMBOTIC_KEYWORDS = [
        # Antiplatelets
        'clopidogrel', 'plavix', 'aspirin', 'asa', 'ticagrelor', 'brilinta',
        'prasugrel', 'effient', 'dipyridamole', 'aggrenox', 'cilostazol', 'pletal',
        # Anticoagulants
        'warfarin', 'coumadin', 'heparin', 'enoxaparin', 'lovenox',
        'rivaroxaban', 'xarelto', 'apixaban', 'eliquis', 'dabigatran', 'pradaxa',
        'edoxaban', 'savaysa', 'fondaparinux', 'arixtra',
        # Thrombolytics
        'alteplase', 'tpa', 'tenecteplase', 'reteplase',
    ]

    ANTITHROMBOTIC_CLASSES = [
        'antiplatelet', 'anticoagulant', 'antithrombotic', 'thrombolytic',
        'blood thinner', 'platelet aggregation inhibitor',
    ]

    def __init__(self):
        super().__init__()
        self.version = INTERPRETER_VERSIONS["medication"]
        self.category = "medication"

    def can_interpret(self, index_entry: Dict) -> bool:
        """Check if this is a medication-related event."""
        category = index_entry.get('category', '')
        return category in ['medication', 'compound']

    def interpret(self, raw_event: Dict, index_entry: Dict) -> InterpretationResult:
        """Extract medications from raw event payload."""
        self._extraction_warnings = []
        medications = []

        payload = raw_event.get('payload', {})
        event_id = raw_event.get('id', '')
        patient_id = index_entry.get('patient_id')
        hints = index_entry.get('extraction_hints', {})

        logger.info(f"[MEDICATION] Interpreting event {event_id[:8]}...")

        # Determine extraction strategy based on hints
        if hints.get('has_athena_class_markers') or hints.get('has_events_array'):
            medications = self._extract_athena_format(payload, event_id)
        else:
            medications = self._extract_generic_format(payload, event_id)

        # Calculate overall confidence
        if medications:
            avg_confidence = sum(m.confidence for m in medications) / len(medications)
        else:
            avg_confidence = 0.0
            self._warn("No medications extracted from payload")

        logger.info(f"[MEDICATION] Extracted {len(medications)} medications (avg confidence: {avg_confidence:.2f})")

        return InterpretationResult(
            category=self.category,
            records=[m.to_dict() for m in medications],
            source_event_id=event_id,
            patient_id=patient_id,
            interpreter_version=self.version,
            interpreted_at=datetime.utcnow().isoformat(),
            confidence=avg_confidence,
            warnings=self._extraction_warnings.copy()
        )

    def _extract_athena_format(self, payload: Dict, event_id: str) -> List[ExtractedMedication]:
        """
        Extract medications from Athena's nested structure.

        Path: payload.active_medications.Medications[].Events[].Instance
        """
        medications = []

        # Navigate to medications array
        med_sources = [
            payload.get('active_medications', {}).get('Medications', []),
            payload.get('medications', {}).get('data', []) if isinstance(payload.get('medications'), dict) else [],
            payload.get('medications', []) if isinstance(payload.get('medications'), list) else [],
            payload.get('Medications', []),
        ]

        med_list = []
        for source in med_sources:
            if source:
                med_list = source
                break

        if not med_list:
            self._warn("No medication array found in Athena structure")
            # Try compound payload structure
            if isinstance(payload.get('medications'), dict):
                data = payload['medications'].get('data', [])
                if data:
                    med_list = data

        for med in med_list:
            if not isinstance(med, dict):
                continue

            # Navigate to Instance within Events
            events = med.get('Events', [])
            if events:
                for event in events:
                    instance = event.get('Instance', {})
                    if instance:
                        extracted = self._extract_from_instance(instance, event, event_id)
                        if extracted:
                            medications.append(extracted)
                            break  # Usually only need first event
            else:
                # Try direct extraction (non-Events format)
                extracted = self._extract_from_flat(med, event_id)
                if extracted:
                    medications.append(extracted)

        return medications

    def _extract_from_instance(self, instance: Dict, event: Dict, event_id: str) -> Optional[ExtractedMedication]:
        """Extract medication from Athena Instance object."""
        confidence = 1.0

        # Primary name field
        name = instance.get('DisplayName', '')
        if not name:
            name = instance.get('Name', '') or instance.get('name', '')
            confidence -= 0.1

        if not name:
            self._warn("No DisplayName in Instance")
            return None

        # Sig (directions)
        sig = instance.get('UnstructuredSig', '')
        if not sig:
            sig = instance.get('Sig', '') or instance.get('sig', '')

        # Nested Medication object
        med_obj = instance.get('Medication', {})
        brand_name = med_obj.get('ProductName', '') or med_obj.get('BrandName', '')
        therapeutic_class = med_obj.get('TherapeuticClass', '')

        # Quantity as dose surrogate
        quantity = instance.get('QuantityValue')
        dose = f"Qty: {quantity}" if quantity else None

        # Status from event type
        event_type = event.get('Type', 'ACTIVE')
        status = 'stopped' if event_type == 'STOP' else 'active'

        # Check if antithrombotic
        is_antithrombotic = self._is_antithrombotic(name, therapeutic_class)

        return ExtractedMedication(
            id=self._generate_id(f"{event_id}:{name}"),
            name=name,
            brand_name=brand_name if brand_name else None,
            dose=dose,
            sig=sig if sig else None,
            therapeutic_class=therapeutic_class if therapeutic_class else None,
            is_antithrombotic=is_antithrombotic,
            status=status,
            source_event_id=event_id,
            confidence=confidence,
            interpreter_version=self.version
        )

    def _extract_from_flat(self, med: Dict, event_id: str) -> Optional[ExtractedMedication]:
        """Extract medication from flat/generic structure."""
        confidence = 0.8  # Lower confidence for non-standard format

        # Try various name fields
        name = (
            med.get('name') or med.get('Name') or
            med.get('medicationName') or med.get('MedicationName') or
            med.get('drugName') or med.get('DrugName') or
            med.get('DisplayName') or med.get('displayName') or
            med.get('description') or ''
        )

        if not name:
            return None

        sig = med.get('sig') or med.get('Sig') or med.get('directions') or ''
        dose = med.get('dose') or med.get('Dose') or med.get('strength') or ''
        therapeutic_class = med.get('therapeuticClass') or med.get('TherapeuticClass') or ''

        is_antithrombotic = self._is_antithrombotic(name, therapeutic_class)

        return ExtractedMedication(
            id=self._generate_id(f"{event_id}:{name}"),
            name=name,
            dose=dose if dose else None,
            sig=sig if sig else None,
            therapeutic_class=therapeutic_class if therapeutic_class else None,
            is_antithrombotic=is_antithrombotic,
            status='active',
            source_event_id=event_id,
            confidence=confidence,
            interpreter_version=self.version
        )

    def _extract_generic_format(self, payload: Dict, event_id: str) -> List[ExtractedMedication]:
        """Extract medications from generic/unknown format."""
        medications = []

        # Ensure payload is a dict
        if not isinstance(payload, dict):
            self._warn(f"Payload is not a dict, got {type(payload).__name__}")
            return medications

        # Try to find any array that looks like medications
        for key in ['medications', 'meds', 'prescriptions', 'drugs']:
            if key in payload:
                data = payload[key]
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            extracted = self._extract_from_flat(item, event_id)
                            if extracted:
                                medications.append(extracted)

        return medications

    def _is_antithrombotic(self, name: str, therapeutic_class: str) -> bool:
        """Check if medication is an antithrombotic (critical for vascular surgery)."""
        # Ensure we have strings, not ints or other types
        name_lower = str(name).lower() if name else ''
        class_lower = str(therapeutic_class).lower() if therapeutic_class else ''

        # Check drug name
        for keyword in self.ANTITHROMBOTIC_KEYWORDS:
            if keyword in name_lower:
                return True

        # Check therapeutic class
        for cls in self.ANTITHROMBOTIC_CLASSES:
            if cls in class_lower:
                return True

        return False


# ==============================================================================
# PROBLEM/DIAGNOSIS INTERPRETER
# ==============================================================================

class ProblemInterpreter(ClinicalInterpreter):
    """
    Extracts problem/diagnosis data from Athena payloads.

    ATHENA STRUCTURE (verified from traffic analysis):
    -------------------------------------------------
    active_problems.Problems[] = {
        Name: "intermittent claudication..."       ← DISPLAY NAME
        Code: {
            Code: "12236951000119108"              ← SNOMED CODE
            Description: "..."
            CodeSet: "SNOMED"
        }
        PatientSnomedICD10s: [                     ← ICD-10 MAPPINGS
            {
                DIAGNOSISCODE: "I70.213"           ← ICD-10 CODE
                FULLDESCRIPTION: "..."
            }
        ]
        Status: "active"
        Primary: false
    }

    VASCULAR SURGERY RELEVANCE:
    ---------------------------
    Flags conditions critical for surgical planning:
    - Peripheral artery disease (PAD)
    - Atherosclerosis
    - Claudication
    - Aneurysms
    - Carotid stenosis
    - Diabetes (wound healing risk)
    - CKD (contrast nephropathy risk)
    """

    # Vascular-relevant ICD-10 code prefixes
    VASCULAR_ICD10_PREFIXES = [
        'I70',   # Atherosclerosis
        'I71',   # Aortic aneurysm/dissection
        'I72',   # Other aneurysms
        'I73',   # Other peripheral vascular diseases
        'I74',   # Arterial embolism/thrombosis
        'I77',   # Other arterial disorders
        'I79',   # Disorders of arteries in diseases classified elsewhere
        'I80',   # Phlebitis and thrombophlebitis
        'I82',   # Venous embolism/thrombosis
        'I83',   # Varicose veins
        'I87',   # Other venous disorders
    ]

    # Cardiovascular risk factor ICD-10 prefixes
    CV_RISK_ICD10_PREFIXES = [
        'E08', 'E09', 'E10', 'E11', 'E13',  # Diabetes
        'E78',   # Disorders of lipoprotein metabolism (hyperlipidemia)
        'I10',   # Essential hypertension
        'I11', 'I12', 'I13',  # Hypertensive heart/kidney disease
        'I25',   # Chronic ischemic heart disease
        'N18',   # Chronic kidney disease
        'Z87.891',  # History of tobacco use
        'F17',   # Nicotine dependence
    ]

    # Vascular keywords for name matching
    VASCULAR_KEYWORDS = [
        'claudication', 'peripheral artery', 'peripheral arterial', 'pad',
        'atherosclerosis', 'stenosis', 'occlusion', 'aneurysm',
        'carotid', 'aortic', 'iliac', 'femoral', 'popliteal', 'tibial',
        'ischemia', 'ischemic', 'gangrene', 'ulcer', 'amputation',
        'thrombosis', 'embolism', 'dvt', 'deep vein', 'pulmonary embolism',
        'varicose', 'venous insufficiency', 'stasis',
    ]

    def __init__(self):
        super().__init__()
        self.version = INTERPRETER_VERSIONS["problem"]
        self.category = "problem"

    def can_interpret(self, index_entry: Dict) -> bool:
        """Check if this is a problem-related event."""
        category = index_entry.get('category', '')
        return category in ['problem', 'compound']

    def interpret(self, raw_event: Dict, index_entry: Dict) -> InterpretationResult:
        """Extract problems/diagnoses from raw event payload."""
        self._extraction_warnings = []
        problems = []

        payload = raw_event.get('payload', {})
        event_id = raw_event.get('id', '')
        patient_id = index_entry.get('patient_id')
        hints = index_entry.get('extraction_hints', {})

        logger.info(f"[PROBLEM] Interpreting event {event_id[:8]}...")

        # Determine extraction strategy
        if hints.get('has_icd10_codes') or hints.get('has_snomed_codes'):
            problems = self._extract_coded_format(payload, event_id)
        else:
            problems = self._extract_generic_format(payload, event_id)

        # Calculate overall confidence
        if problems:
            avg_confidence = sum(p.confidence for p in problems) / len(problems)
        else:
            avg_confidence = 0.0
            self._warn("No problems extracted from payload")

        logger.info(f"[PROBLEM] Extracted {len(problems)} problems (avg confidence: {avg_confidence:.2f})")

        return InterpretationResult(
            category=self.category,
            records=[p.to_dict() for p in problems],
            source_event_id=event_id,
            patient_id=patient_id,
            interpreter_version=self.version,
            interpreted_at=datetime.utcnow().isoformat(),
            confidence=avg_confidence,
            warnings=self._extraction_warnings.copy()
        )

    def _extract_coded_format(self, payload: Dict, event_id: str) -> List[ExtractedProblem]:
        """Extract problems from Athena's coded structure."""
        problems = []

        # Navigate to problems array
        prob_sources = [
            payload.get('active_problems', {}).get('Problems', []),
            payload.get('problems', {}).get('data', []) if isinstance(payload.get('problems'), dict) else [],
            payload.get('problems', []) if isinstance(payload.get('problems'), list) else [],
            payload.get('Problems', []),
            payload.get('conditions', []),
        ]

        prob_list = []
        for source in prob_sources:
            if source:
                prob_list = source
                break

        # Also check for IMO Health categorized format
        if not prob_list and 'categories' in payload:
            for category in payload.get('categories', []):
                cat_problems = category.get('problems', [])
                prob_list.extend(cat_problems)

        for prob in prob_list:
            if not isinstance(prob, dict):
                continue

            extracted = self._extract_athena_problem(prob, event_id)
            if extracted:
                problems.append(extracted)

        return problems

    def _extract_athena_problem(self, prob: Dict, event_id: str) -> Optional[ExtractedProblem]:
        """Extract problem from Athena structure."""
        confidence = 1.0

        # Display name (Athena uses PascalCase 'Name')
        display_name = (
            prob.get('Name') or prob.get('name') or
            prob.get('description') or prob.get('Description') or
            prob.get('title') or ''
        )

        if not display_name:
            self._warn("No display name found for problem")
            return None

        # SNOMED from Code object
        code_obj = prob.get('Code', {})
        snomed_code = None
        snomed_desc = None
        if isinstance(code_obj, dict):
            snomed_code = code_obj.get('Code', '')
            snomed_desc = code_obj.get('Description', '')
            if not display_name:
                display_name = snomed_desc

        # ICD-10 from PatientSnomedICD10s array
        icd10_code = None
        icd10_desc = None
        icd10_mappings = prob.get('PatientSnomedICD10s', [])
        if isinstance(icd10_mappings, list) and icd10_mappings:
            first_mapping = icd10_mappings[0]
            if isinstance(first_mapping, dict):
                icd10_code = first_mapping.get('DIAGNOSISCODE', '')
                icd10_desc = first_mapping.get('FULLDESCRIPTION', '')
                if not display_name:
                    display_name = icd10_desc

        # Fallback ICD-10 extraction
        if not icd10_code:
            icd10_code = prob.get('icd10') or prob.get('ICD10') or prob.get('code') or ''
            confidence -= 0.1

        # Status
        status = prob.get('Status') or prob.get('status') or 'active'
        if status is None:
            status = 'active'

        # Primary diagnosis flag
        is_primary = prob.get('Primary', False) or prob.get('primary', False)

        # Check if vascular-relevant
        is_vascular = self._is_vascular(display_name, icd10_code)
        is_cv_risk = self._is_cv_risk_factor(icd10_code)

        return ExtractedProblem(
            id=self._generate_id(f"{event_id}:{display_name}:{icd10_code}"),
            display_name=display_name,
            icd10_code=icd10_code if icd10_code else None,
            icd10_description=icd10_desc if icd10_desc else None,
            snomed_code=snomed_code if snomed_code else None,
            snomed_description=snomed_desc if snomed_desc else None,
            is_vascular=is_vascular,
            is_cardiovascular_risk=is_cv_risk,
            clinical_status=str(status).lower(),
            is_primary=is_primary,
            source_event_id=event_id,
            confidence=confidence,
            interpreter_version=self.version
        )

    def _extract_generic_format(self, payload: Dict, event_id: str) -> List[ExtractedProblem]:
        """Extract problems from generic/unknown format."""
        problems = []

        for key in ['problems', 'diagnoses', 'conditions']:
            if key in payload:
                data = payload[key]
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            extracted = self._extract_flat_problem(item, event_id)
                            if extracted:
                                problems.append(extracted)

        return problems

    def _extract_flat_problem(self, prob: Dict, event_id: str) -> Optional[ExtractedProblem]:
        """Extract problem from flat structure."""
        confidence = 0.7  # Lower confidence for non-standard format

        display_name = (
            prob.get('name') or prob.get('description') or
            prob.get('title') or prob.get('display') or ''
        )

        if not display_name:
            return None

        icd10_code = prob.get('icd10') or prob.get('code') or ''

        is_vascular = self._is_vascular(display_name, icd10_code)
        is_cv_risk = self._is_cv_risk_factor(icd10_code)

        return ExtractedProblem(
            id=self._generate_id(f"{event_id}:{display_name}"),
            display_name=display_name,
            icd10_code=icd10_code if icd10_code else None,
            is_vascular=is_vascular,
            is_cardiovascular_risk=is_cv_risk,
            clinical_status='active',
            source_event_id=event_id,
            confidence=confidence,
            interpreter_version=self.version
        )

    def _is_vascular(self, name: str, icd10_code: str) -> bool:
        """Check if problem is vascular-relevant."""
        name_lower = name.lower()

        # Check keywords in name
        for keyword in self.VASCULAR_KEYWORDS:
            if keyword in name_lower:
                return True

        # Check ICD-10 prefix
        if icd10_code:
            code_upper = icd10_code.upper().replace('.', '')
            for prefix in self.VASCULAR_ICD10_PREFIXES:
                if code_upper.startswith(prefix):
                    return True

        return False

    def _is_cv_risk_factor(self, icd10_code: str) -> bool:
        """Check if problem is a cardiovascular risk factor."""
        if not icd10_code:
            return False

        code_upper = icd10_code.upper().replace('.', '')
        for prefix in self.CV_RISK_ICD10_PREFIXES:
            if code_upper.startswith(prefix.replace('.', '')):
                return True

        return False


# ==============================================================================
# INTERPRETER REGISTRY
# ==============================================================================

class InterpreterRegistry:
    """
    Registry for managing clinical interpreters.

    Provides:
    - Interpreter registration and lookup
    - Automatic interpreter selection based on event category
    - Batch interpretation of indexed events
    """

    def __init__(self):
        self._interpreters: Dict[str, ClinicalInterpreter] = {}
        self._register_default_interpreters()

    def _register_default_interpreters(self):
        """Register built-in interpreters."""
        self.register(MedicationInterpreter())
        self.register(ProblemInterpreter())
        logger.info(f"[REGISTRY] Registered {len(self._interpreters)} interpreters")

    def register(self, interpreter: ClinicalInterpreter):
        """Register an interpreter."""
        self._interpreters[interpreter.category] = interpreter
        logger.debug(f"[REGISTRY] Registered {interpreter.category} interpreter v{interpreter.version}")

    def get_interpreter(self, category: str) -> Optional[ClinicalInterpreter]:
        """Get interpreter by category."""
        return self._interpreters.get(category)

    def find_interpreters(self, index_entry: Dict) -> List[ClinicalInterpreter]:
        """Find all interpreters that can handle an indexed event."""
        matching = []
        for interpreter in self._interpreters.values():
            if interpreter.can_interpret(index_entry):
                matching.append(interpreter)
        return matching

    def interpret_event(
        self,
        raw_event: Dict,
        index_entry: Dict
    ) -> List[InterpretationResult]:
        """
        Interpret a raw event using all applicable interpreters.

        Args:
            raw_event: Raw event from Layer 1
            index_entry: Index entry from Layer 2

        Returns:
            List of InterpretationResults from all applicable interpreters
        """
        results = []

        interpreters = self.find_interpreters(index_entry)
        if not interpreters:
            logger.debug(f"[REGISTRY] No interpreters for category: {index_entry.get('category')}")
            return results

        for interpreter in interpreters:
            try:
                result = interpreter.interpret(raw_event, index_entry)
                if result.records:
                    results.append(result)
            except Exception as e:
                logger.error(f"[REGISTRY] Interpreter {interpreter.category} failed: {e}")

        return results

    def get_versions(self) -> Dict[str, str]:
        """Get all interpreter versions."""
        return {cat: interp.version for cat, interp in self._interpreters.items()}


# ==============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ==============================================================================

# Global registry instance
_registry: Optional[InterpreterRegistry] = None


def get_registry() -> InterpreterRegistry:
    """Get or create the global interpreter registry."""
    global _registry
    if _registry is None:
        _registry = InterpreterRegistry()
    return _registry


def interpret_event(raw_event: Dict, index_entry: Dict) -> List[InterpretationResult]:
    """
    Convenience function to interpret an event using the global registry.

    Args:
        raw_event: Raw event from Layer 1 Event Store
        index_entry: Index entry from Layer 2 Event Indexer

    Returns:
        List of InterpretationResults
    """
    return get_registry().interpret_event(raw_event, index_entry)


def get_interpreter_versions() -> Dict[str, str]:
    """Get versions of all registered interpreters."""
    return get_registry().get_versions()
