"""
FHIR Converter: Transforms proprietary AthenaNet JSON to FHIR R4 resources.

This module handles the ETL (Extract, Transform, Load) process for normalizing
AthenaNet's non-standard API responses into valid FHIR R4 structures.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import hashlib

from schemas import (
    FHIRPatient, FHIRObservation, FHIRCondition, FHIRMedication,
    VitalComponent, Patient, Vitals, LogEntry
)

# Get logger from main module
logger = logging.getLogger("shadow-ehr")


def generate_id(data: Any) -> str:
    """Generate a deterministic ID from data."""
    content = str(data).encode('utf-8')
    return hashlib.md5(content).hexdigest()[:12]


def normalize_date(date_str: Optional[str]) -> str:
    """Normalize various date formats to ISO-8601."""
    if not date_str:
        return ""

    # Common AthenaNet date formats
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
        "%B %d, %Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str  # Return original if no format matches


def extract_patient_id(endpoint: str) -> Optional[str]:
    """Extract patient ID from AthenaNet API endpoint."""
    patterns = [
        r'/chart/patient/(\d+)',
        r'/chart/(\d+)',
        r'/patients/(\d+)',
        r'/patient/(\d+)',
        r'/encounter/(\d+)',
        r'patientid[=/](\d+)',
        r'patient_id[=/](\d+)',
        r'patient[=/](\d+)',
        r'chartid[=/](\d+)',
        r'/api/\d+/chart/(\d+)',
        r'/api/v\d+/patients?/(\d+)',
        # AthenaNet specific patterns
        r'athena[^/]*/(\d{5,})',  # Athena IDs are typically 5+ digits
        r'/(\d{6,})/(?:vitals|meds|problems|labs|allergies)',  # ID before resource type
    ]

    for pattern in patterns:
        match = re.search(pattern, endpoint, re.IGNORECASE)
        if match:
            logger.debug(f"[FHIR] Patient ID extracted: {match.group(1)} from pattern: {pattern}")
            return match.group(1)

    # Fallback: look for any 6+ digit number that might be a patient ID
    fallback = re.search(r'/(\d{6,})(?:/|$|\?)', endpoint)
    if fallback:
        logger.debug(f"[FHIR] Patient ID extracted (fallback): {fallback.group(1)}")
        return fallback.group(1)

    logger.debug(f"[FHIR] No patient ID found in: {endpoint[:100]}")
    return None


def detect_record_type(endpoint: str, payload: Any) -> str:
    """Detect the type of clinical record from endpoint and payload."""
    endpoint_lower = endpoint.lower()
    logger.debug(f"[FHIR] Detecting record type for: {endpoint_lower[:80]}...")

    # =========================================================================
    # ATHENA-SPECIFIC URL PATTERNS (query parameter based)
    # Pattern: /ax/data?sources=<type>&...
    # =========================================================================
    if 'sources=' in endpoint_lower:
        if 'active_medications' in endpoint_lower or 'medications' in endpoint_lower:
            logger.info(f"[FHIR] Record type: MEDICATION (Athena sources param)")
            return 'medication'
        elif 'active_problems' in endpoint_lower or 'chart_overview_problems' in endpoint_lower or 'historical_problems' in endpoint_lower:
            logger.info(f"[FHIR] Record type: PROBLEM (Athena sources param)")
            return 'problem'
        elif 'allergies' in endpoint_lower:
            logger.info(f"[FHIR] Record type: ALLERGY (Athena sources param)")
            return 'allergy'
        elif 'measurements' in endpoint_lower or 'vitals' in endpoint_lower:
            logger.info(f"[FHIR] Record type: VITAL (Athena sources param)")
            return 'vital'
        elif 'demographics' in endpoint_lower:
            logger.info(f"[FHIR] Record type: PATIENT (Athena sources param)")
            return 'patient'
        elif 'lab' in endpoint_lower or 'results' in endpoint_lower:
            logger.info(f"[FHIR] Record type: LAB (Athena sources param)")
            return 'lab'
        elif 'document' in endpoint_lower or 'external_document' in endpoint_lower:
            logger.info(f"[FHIR] Record type: NOTE (Athena sources param)")
            return 'note'

    # =========================================================================
    # STANDARD URL PATH PATTERNS
    # =========================================================================
    if '/vitals' in endpoint_lower or '/vital' in endpoint_lower:
        logger.info(f"[FHIR] Record type: VITAL")
        return 'vital'
    elif '/medication' in endpoint_lower or '/med' in endpoint_lower or '/prescription' in endpoint_lower:
        logger.info(f"[FHIR] Record type: MEDICATION")
        return 'medication'
    elif '/problem' in endpoint_lower or '/condition' in endpoint_lower or '/diagnosis' in endpoint_lower:
        logger.info(f"[FHIR] Record type: PROBLEM")
        return 'problem'
    elif '/lab' in endpoint_lower or '/result' in endpoint_lower:
        logger.info(f"[FHIR] Record type: LAB")
        return 'lab'
    elif '/patient' in endpoint_lower and '/chart' in endpoint_lower:
        logger.info(f"[FHIR] Record type: PATIENT")
        return 'patient'
    elif '/note' in endpoint_lower or '/encounter' in endpoint_lower:
        logger.info(f"[FHIR] Record type: NOTE")
        return 'note'
    elif '/imaging' in endpoint_lower or '/radiology' in endpoint_lower:
        logger.info(f"[FHIR] Record type: IMAGING")
        return 'imaging'
    elif '/allerg' in endpoint_lower:
        logger.info(f"[FHIR] Record type: ALLERGY")
        return 'allergy'

    # Fallback: check payload structure
    logger.debug(f"[FHIR] No endpoint match, checking payload keys...")
    if isinstance(payload, dict):
        keys = list(payload.keys())[:10]
        logger.debug(f"[FHIR] Payload keys: {keys}")
        if 'vitals' in payload or 'bloodPressure' in payload:
            logger.info(f"[FHIR] Record type: VITAL (from payload)")
            return 'vital'
        if 'medications' in payload or 'prescriptions' in payload:
            logger.info(f"[FHIR] Record type: MEDICATION (from payload)")
            return 'medication'
        if 'problems' in payload or 'diagnoses' in payload:
            logger.info(f"[FHIR] Record type: PROBLEM (from payload)")
            return 'problem'
        if 'firstName' in payload or 'lastName' in payload or 'patientName' in payload:
            logger.info(f"[FHIR] Record type: PATIENT (from payload)")
            return 'patient'

    logger.warning(f"[FHIR] Record type: UNKNOWN")
    return 'unknown'


def convert_vitals(payload: Any) -> FHIRObservation:
    """Convert AthenaNet vitals to FHIR Observation."""
    components = []

    if isinstance(payload, dict):
        # Extract blood pressure
        bp_systolic = payload.get('systolic') or payload.get('bpSystolic') or payload.get('bloodPressure', {}).get('systolic')
        bp_diastolic = payload.get('diastolic') or payload.get('bpDiastolic') or payload.get('bloodPressure', {}).get('diastolic')

        if bp_systolic and bp_diastolic:
            components.append(VitalComponent(
                code="blood-pressure",
                display="Blood Pressure",
                value=f"{bp_systolic}/{bp_diastolic}",
                unit="mmHg"
            ))

        # Heart rate
        hr = payload.get('heartRate') or payload.get('pulse') or payload.get('hr')
        if hr:
            components.append(VitalComponent(
                code="heart-rate",
                display="Heart Rate",
                value=int(hr),
                unit="bpm"
            ))

        # Temperature
        temp = payload.get('temperature') or payload.get('temp')
        if temp:
            components.append(VitalComponent(
                code="temperature",
                display="Temperature",
                value=float(temp),
                unit="°F"
            ))

        # SpO2
        spo2 = payload.get('oxygenSaturation') or payload.get('spo2') or payload.get('o2sat')
        if spo2:
            components.append(VitalComponent(
                code="oxygen-saturation",
                display="Oxygen Saturation",
                value=int(spo2),
                unit="%"
            ))

        # Weight
        weight = payload.get('weight')
        if weight:
            components.append(VitalComponent(
                code="weight",
                display="Weight",
                value=float(weight),
                unit="lbs"
            ))

        # Height
        height = payload.get('height')
        if height:
            components.append(VitalComponent(
                code="height",
                display="Height",
                value=height,
                unit="in"
            ))

    return FHIRObservation(
        id=generate_id(payload),
        code="vital-signs",
        display="Vital Signs Panel",
        components=components,
        effectiveDateTime=datetime.now().isoformat()
    )


def convert_medications(payload: Any) -> List[FHIRMedication]:
    """Convert AthenaNet medications to FHIR MedicationStatement list."""
    medications = []

    # Handle various payload structures
    med_list = []
    if isinstance(payload, list):
        med_list = payload
    elif isinstance(payload, dict):
        # DEBUG: Log all top-level keys to understand Athena's structure
        top_keys = list(payload.keys())[:15]
        logger.info(f"[FHIR] MEDICATION payload top-level keys: {top_keys}")

        # Standard keys
        med_list = payload.get('medications') or payload.get('prescriptions') or payload.get('meds') or []

        # Athena-specific: sources=active_medications returns nested data
        if not med_list and 'active_medications' in payload:
            athena_meds = payload.get('active_medications', {})
            logger.info(f"[FHIR] Found 'active_medications' key, type: {type(athena_meds).__name__}")
            if isinstance(athena_meds, dict):
                inner_keys = list(athena_meds.keys())[:10]
                logger.info(f"[FHIR] active_medications dict keys: {inner_keys}")
                med_list = athena_meds.get('medications', []) or athena_meds.get('data', []) or athena_meds.get('Medications', []) or []
                # Try nested structure: active_medications.Medications (Athena uses PascalCase)
                if not med_list:
                    for key in athena_meds.keys():
                        if 'medication' in key.lower():
                            logger.info(f"[FHIR] Found medication-like key: {key}")
                            val = athena_meds.get(key)
                            if isinstance(val, list):
                                med_list = val
                                break
            elif isinstance(athena_meds, list):
                med_list = athena_meds
            logger.info(f"[FHIR] Extracted {len(med_list)} medications from Athena active_medications")

        # Athena alternative: data key with medications inside
        if not med_list and 'data' in payload:
            data = payload.get('data', {})
            if isinstance(data, dict):
                med_list = data.get('medications', []) or data.get('active_medications', []) or []
            elif isinstance(data, list):
                # Check if items look like medications
                for item in data:
                    if isinstance(item, dict) and any(k in item for k in ['medicationName', 'drugName', 'medication', 'rxnorm']):
                        med_list = data
                        break

        if not med_list and 'medication' in payload:
            med_list = [payload]

    # DEBUG: Log first medication object structure
    if med_list and isinstance(med_list[0], dict):
        first_med_keys = list(med_list[0].keys())[:15]
        logger.info(f"[FHIR] First medication object keys: {first_med_keys}")

    for med in med_list:
        if isinstance(med, dict):
            name = ''
            dose = ''
            freq = ''
            status = 'active'

            # ATHENA SPECIFIC: Medication info is in Events array
            # Structure: {'__CLASS__': 'Athena::Chart::Entity::Medication', 'Events': [...]}
            if 'Events' in med and isinstance(med.get('Events'), list):
                events = med.get('Events', [])
                if events:
                    # Log first event structure for debugging
                    first_event = events[0] if events else {}
                    if isinstance(first_event, dict):
                        event_keys = list(first_event.keys())[:15]
                        logger.debug(f"[FHIR] Athena Event keys: {event_keys}")

                    # Extract from first event (most recent)
                    for event in events:
                        if isinstance(event, dict):
                            # Try various Athena medication name fields
                            name = (event.get('MedicationName') or event.get('NDCDescription') or
                                    event.get('BrandName') or event.get('GenericName') or
                                    event.get('DrugName') or event.get('Name') or
                                    event.get('Description') or '')
                            dose = (event.get('StrengthDescription') or event.get('Strength') or
                                    event.get('Dosage') or event.get('Dose') or '')
                            freq = (event.get('SigDescription') or event.get('Sig') or
                                    event.get('Frequency') or event.get('Directions') or '')
                            status = event.get('Status') or event.get('MedicationStatus') or 'active'

                            if name:
                                break  # Found a name, stop searching

            # Standard keys (camelCase) - fallback
            if not name:
                name = med.get('medicationName') or med.get('name') or med.get('drugName') or med.get('description') or ''
            # Athena PascalCase keys - fallback
            if not name:
                name = med.get('MedicationName') or med.get('Name') or med.get('DrugName') or med.get('Description') or ''
            # Athena nested structure: might have 'Medication' -> 'Name'
            if not name and 'Medication' in med:
                inner = med.get('Medication', {})
                name = inner.get('Name') or inner.get('DrugName') or inner.get('Description') or ''
            # Try NDCDescription or BrandName (common in Athena)
            if not name:
                name = med.get('NDCDescription') or med.get('BrandName') or med.get('GenericName') or ''

            if not dose:
                dose = med.get('dosage') or med.get('dose') or med.get('strength') or ''
            if not dose:
                dose = med.get('Dosage') or med.get('Dose') or med.get('Strength') or med.get('StrengthDescription') or ''

            if not freq:
                freq = med.get('frequency') or med.get('sig') or med.get('directions') or ''
            if not freq:
                freq = med.get('Frequency') or med.get('Sig') or med.get('Directions') or med.get('SigDescription') or ''

            if name:
                medications.append(FHIRMedication(
                    id=generate_id(med),
                    name=str(name),
                    dose=str(dose) if dose else None,
                    frequency=str(freq) if freq else None,
                    status=str(status)
                ))
                logger.debug(f"[FHIR] Extracted medication: {name[:50]}")
            else:
                logger.warning(f"[FHIR] Could not extract medication name. Keys: {list(med.keys())[:10]}")
        elif isinstance(med, str):
            medications.append(FHIRMedication(
                id=generate_id(med),
                name=med
            ))

    return medications


def convert_problems(payload: Any) -> List[FHIRCondition]:
    """Convert AthenaNet problems/diagnoses to FHIR Condition list."""
    conditions = []

    # Handle various payload structures
    prob_list = []
    if isinstance(payload, list):
        prob_list = payload
    elif isinstance(payload, dict):
        # Handle IMO Health categorized format: {'categories': [{'problems': [...]}]}
        if 'categories' in payload:
            for category in payload.get('categories', []):
                cat_problems = category.get('problems', [])
                prob_list.extend(cat_problems)
        else:
            prob_list = payload.get('problems') or payload.get('diagnoses') or payload.get('conditions') or []
            if not prob_list and 'problem' in payload:
                prob_list = [payload]

    for prob in prob_list:
        if isinstance(prob, dict):
            code = prob.get('icd10') or prob.get('code') or prob.get('diagnosisCode') or prob.get('lexical_code') or ''
            display = prob.get('description') or prob.get('title') or prob.get('name') or prob.get('problemName') or ''
            status = prob.get('status', 'active')
            onset = normalize_date(prob.get('onsetDate') or prob.get('startDate'))

            conditions.append(FHIRCondition(
                id=generate_id(prob),
                code=str(code),
                display=str(display),
                clinicalStatus=str(status),
                onsetDateTime=onset if onset else None
            ))
        elif isinstance(prob, str):
            conditions.append(FHIRCondition(
                id=generate_id(prob),
                display=prob
            ))

    return conditions


def convert_patient(payload: Any, patient_id: Optional[str] = None) -> FHIRPatient:
    """Convert AthenaNet patient data to FHIR Patient resource."""
    if not isinstance(payload, dict):
        return FHIRPatient(id=patient_id or generate_id(payload))

    # Extract name components
    first_name = payload.get('firstName') or payload.get('first_name') or payload.get('givenName') or ''
    last_name = payload.get('lastName') or payload.get('last_name') or payload.get('familyName') or ''
    full_name = payload.get('patientName') or payload.get('name') or f"{first_name} {last_name}".strip()

    # Extract identifiers
    identifiers = []
    mrn = payload.get('mrn') or payload.get('patientId') or payload.get('patient_id') or patient_id
    if mrn:
        identifiers.append({"system": "mrn", "value": str(mrn)})

    # Extract other fields
    dob = normalize_date(payload.get('dob') or payload.get('dateOfBirth') or payload.get('birthDate'))
    gender = payload.get('gender') or payload.get('sex') or ''

    return FHIRPatient(
        id=patient_id or generate_id(payload),
        identifier=identifiers,
        name={"full": full_name, "given": [first_name] if first_name else [], "family": last_name},
        birthDate=dob if dob else None,
        gender=gender.lower() if gender else None
    )


def convert_to_fhir(endpoint: str, method: str, payload: Any) -> Tuple[str, Any]:
    """
    Main conversion function. Detects record type and converts to appropriate FHIR resource.

    IMPORTANT: Handles compound payloads that contain multiple data types
    (e.g., {'medications': [...], 'vitals': {...}, 'labs': [...]})

    Returns:
        Tuple of (record_type, fhir_resource)
    """
    # Check for compound payload FIRST (contains multiple data types)
    if isinstance(payload, dict):
        compound_keys = {'medications', 'vitals', 'labs', 'orders', 'problems', 'allergies'}
        present_keys = set(payload.keys()) & compound_keys

        if len(present_keys) >= 2:
            logger.info(f"[FHIR] COMPOUND PAYLOAD detected with keys: {present_keys}")
            # Return as compound type with all data
            result = {'_compound': True}

            if 'medications' in payload and payload['medications']:
                meds = payload['medications']
                if isinstance(meds, list):
                    result['medications'] = [m.dict() for m in convert_medications(meds)]
                    logger.info(f"[FHIR] Extracted {len(result['medications'])} medications from compound payload")

            if 'vitals' in payload and payload['vitals']:
                result['vitals'] = convert_vitals(payload['vitals'])

            if 'labs' in payload and payload['labs']:
                result['labs'] = payload['labs']

            if 'problems' in payload and payload['problems']:
                result['conditions'] = [c.dict() for c in convert_problems(payload['problems'])]

            if 'allergies' in payload and payload['allergies']:
                result['allergies'] = payload['allergies']

            return 'compound', result

    record_type = detect_record_type(endpoint, payload)

    if record_type == 'vital':
        return record_type, convert_vitals(payload)
    elif record_type == 'medication':
        return record_type, {"medications": [m.dict() for m in convert_medications(payload)]}
    elif record_type == 'problem':
        return record_type, {"conditions": [c.dict() for c in convert_problems(payload)]}
    elif record_type == 'patient':
        patient_id = extract_patient_id(endpoint)
        return record_type, convert_patient(payload, patient_id)
    else:
        # Return raw payload for unknown types
        return record_type, payload


def build_patient_from_aggregated_data(
    patient_id: str,
    patient_data: Optional[Dict] = None,
    vitals_data: Optional[Dict] = None,
    medications_data: Optional[List] = None,
    problems_data: Optional[List] = None
) -> Patient:
    """
    Build a complete Patient object from aggregated FHIR data.
    This is used to create the frontend-ready patient structure.
    """
    # Extract patient info
    name = "Unknown"
    mrn = f"MRN-{patient_id}"
    dob = ""
    gender = ""

    if patient_data:
        if isinstance(patient_data, dict):
            name_obj = patient_data.get('name', {})
            if isinstance(name_obj, dict):
                name = name_obj.get('full', 'Unknown')
            identifiers = patient_data.get('identifier', [])
            for ident in identifiers:
                if ident.get('system') == 'mrn':
                    mrn = ident.get('value', mrn)
            dob = patient_data.get('birthDate', '')
            gender = patient_data.get('gender', '')

    # Extract vitals
    vitals = Vitals()
    if vitals_data:
        components = vitals_data.get('components', [])
        for comp in components:
            code = comp.get('code', '')
            value = comp.get('value')
            if code == 'blood-pressure' and value:
                vitals.bp = str(value)
            elif code == 'heart-rate' and value:
                vitals.hr = int(value)
            elif code == 'temperature' and value:
                vitals.temp = float(value)
            elif code == 'oxygen-saturation' and value:
                vitals.spo2 = int(value)

    # Extract conditions
    conditions = []
    if problems_data:
        for prob in problems_data:
            if isinstance(prob, dict):
                display = prob.get('display', '')
                if display:
                    conditions.append(display)

    # Extract medications
    medications = []
    if medications_data:
        for med in medications_data:
            if isinstance(med, dict):
                med_name = med.get('name', '')
                dose = med.get('dose', '')
                if med_name:
                    med_str = f"{med_name} {dose}".strip() if dose else med_name
                    medications.append(med_str)

    return Patient(
        id=patient_id,
        mrn=mrn,
        name=name,
        dob=dob,
        gender=gender,
        lastEncounter=datetime.now().strftime("%Y-%m-%d"),
        conditions=conditions,
        medications=medications,
        vitals=vitals,
        notes=""
    )


def create_log_entry(endpoint: str, method: str, payload: Any, fhir_resource: Any) -> LogEntry:
    """Create a LogEntry for the frontend live log."""
    payload_size = len(str(payload).encode('utf-8')) if payload else 0

    return LogEntry(
        id=generate_id(f"{endpoint}{datetime.now().isoformat()}"),
        timestamp=datetime.now().isoformat(),
        method=method,
        endpoint=endpoint,
        status=200,
        size=f"{round(payload_size / 1024, 1)}kb",
        payload=fhir_resource
    )
