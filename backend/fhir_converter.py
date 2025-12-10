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
    logger.debug(f"[FHIR] Detecting record type for: {endpoint_lower[:50]}...")

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
        med_list = payload.get('medications') or payload.get('prescriptions') or payload.get('meds') or []
        if not med_list and 'medication' in payload:
            med_list = [payload]

    for med in med_list:
        if isinstance(med, dict):
            name = med.get('medicationName') or med.get('name') or med.get('drugName') or med.get('description') or ''
            dose = med.get('dosage') or med.get('dose') or med.get('strength') or ''
            freq = med.get('frequency') or med.get('sig') or med.get('directions') or ''
            status = med.get('status', 'active')

            medications.append(FHIRMedication(
                id=generate_id(med),
                name=str(name),
                dose=str(dose) if dose else None,
                frequency=str(freq) if freq else None,
                status=str(status)
            ))
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

    Returns:
        Tuple of (record_type, fhir_resource)
    """
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
