"""
Vascular Surgery Data Parser

Extracts surgery-relevant clinical data from raw EHR payloads.
Optimized for pre-op, intra-op, and post-op vascular surgery workflows.
"""

import re
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

logger = logging.getLogger("shadow-ehr")


# ============================================================
# VASCULAR-SPECIFIC DATA MODELS
# ============================================================

class AntithromboticMed(BaseModel):
    """Antithrombotic medication with surgical relevance."""
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    last_filled: Optional[str] = None
    category: str  # antiplatelet, anticoagulant, direct_oral
    hold_days_preop: int = 0  # Recommended hold time before surgery
    bridging_required: bool = False
    reversal_agent: Optional[str] = None


class RenalFunction(BaseModel):
    """Renal function panel for contrast considerations."""
    creatinine: Optional[float] = None
    creatinine_date: Optional[str] = None
    egfr: Optional[float] = None
    egfr_date: Optional[str] = None
    bun: Optional[float] = None
    contrast_risk: str = "unknown"  # low, moderate, high, contraindicated


class CoagulationPanel(BaseModel):
    """Coagulation status for surgical planning."""
    pt: Optional[float] = None
    inr: Optional[float] = None
    ptt: Optional[float] = None
    pt_date: Optional[str] = None
    therapeutic_range: bool = False
    reversal_needed: bool = False


class CardiacClearance(BaseModel):
    """Cardiac risk assessment summary."""
    cleared: Optional[bool] = None
    clearance_date: Optional[str] = None
    ejection_fraction: Optional[float] = None
    stress_test_date: Optional[str] = None
    stress_test_result: Optional[str] = None
    rcri_score: Optional[int] = None  # Revised Cardiac Risk Index
    notes: Optional[str] = None


class VascularHistory(BaseModel):
    """Previous vascular interventions."""
    procedure: str
    date: Optional[str] = None
    location: Optional[str] = None  # Anatomic location (e.g., "Left SFA")
    details: Optional[str] = None
    stent_type: Optional[str] = None


class CriticalAllergy(BaseModel):
    """Surgically relevant allergies."""
    allergen: str
    reaction: Optional[str] = None
    severity: str = "unknown"  # mild, moderate, severe
    surgical_implication: Optional[str] = None


class Diagnosis(BaseModel):
    """A patient diagnosis/problem with ICD-10 code."""
    name: str
    icd10_code: Optional[str] = None
    status: str = "active"  # active, resolved, etc.
    onset_date: Optional[str] = None


class Document(BaseModel):
    """A clinical document, report, or image."""
    id: str
    title: str
    category: str  # CTA, Ultrasound, Operative, Pathology, Lab, Note, Other
    date: Optional[str] = None
    author: Optional[str] = None
    url: Optional[str] = None


class VascularProfile(BaseModel):
    """Complete vascular surgery profile for a patient."""
    patient_id: str
    mrn: str
    name: str

    # Pre-op critical data
    antithrombotics: List[AntithromboticMed] = []
    renal_function: Optional[RenalFunction] = None
    coagulation: Optional[CoagulationPanel] = None
    cardiac_clearance: Optional[CardiacClearance] = None
    critical_allergies: List[CriticalAllergy] = []

    # Diagnoses/Problems - ALL active problems for the patient
    diagnoses: List[Diagnosis] = []

    # Clinical documents (categorized)
    documents: List[Document] = []

    # Surgical history
    vascular_history: List[VascularHistory] = []

    # Risk flags
    high_bleeding_risk: bool = False
    contrast_caution: bool = False
    cardiac_risk: str = "unknown"

    # Raw data references
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


# ============================================================
# MEDICATION CLASSIFICATION
# ============================================================

ANTITHROMBOTIC_DRUGS = {
    # Antiplatelets
    "aspirin": {"category": "antiplatelet", "hold_days": 0, "bridging": False},
    "clopidogrel": {"category": "antiplatelet", "hold_days": 5, "bridging": False},
    "plavix": {"category": "antiplatelet", "hold_days": 5, "bridging": False},
    "prasugrel": {"category": "antiplatelet", "hold_days": 7, "bridging": False},
    "effient": {"category": "antiplatelet", "hold_days": 7, "bridging": False},
    "ticagrelor": {"category": "antiplatelet", "hold_days": 5, "bridging": False},
    "brilinta": {"category": "antiplatelet", "hold_days": 5, "bridging": False},
    
    # Direct Oral Anticoagulants (DOACs)
    "apixaban": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    "eliquis": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    "rivaroxaban": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    "xarelto": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    "dabigatran": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Idarucizumab"},
    "pradaxa": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Idarucizumab"},
    "edoxaban": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    "savaysa": {"category": "doac", "hold_days": 2, "bridging": False, "reversal": "Andexanet alfa"},
    
    # Vitamin K Antagonists
    "warfarin": {"category": "vka", "hold_days": 5, "bridging": True, "reversal": "Vitamin K / FFP / PCC"},
    "coumadin": {"category": "vka", "hold_days": 5, "bridging": True, "reversal": "Vitamin K / FFP / PCC"},
    
    # Injectable Anticoagulants
    "heparin": {"category": "injectable", "hold_days": 0, "bridging": False, "reversal": "Protamine"},
    "enoxaparin": {"category": "injectable", "hold_days": 1, "bridging": False, "reversal": "Protamine (partial)"},
    "lovenox": {"category": "injectable", "hold_days": 1, "bridging": False, "reversal": "Protamine (partial)"},
}

CONTRAST_ALLERGIES = ["contrast", "iodine", "iodinated", "gadolinium"]
SURGICAL_ALLERGIES = ["latex", "heparin", "protamine", "chlorhexidine"]


# ============================================================
# PARSER FUNCTIONS
# ============================================================

def parse_antithrombotics(medications: List[Any]) -> List[AntithromboticMed]:
    """Extract antithrombotic medications from medication list."""
    results = []
    
    for med in medications:
        med_str = str(med).lower() if med else ""
        med_name = ""
        
        # Extract medication name
        if isinstance(med, dict):
            med_name = (med.get("name") or med.get("medicationName") or 
                       med.get("drugName") or med.get("description") or "").lower()
        else:
            med_name = med_str
        
        # Check against known antithrombotics
        for drug, info in ANTITHROMBOTIC_DRUGS.items():
            if drug in med_name:
                # Extract dose if available
                dose = None
                if isinstance(med, dict):
                    dose = med.get("dose") or med.get("dosage") or med.get("strength")
                
                results.append(AntithromboticMed(
                    name=drug.title(),
                    dose=str(dose) if dose else None,
                    frequency=med.get("frequency") if isinstance(med, dict) else None,
                    last_filled=med.get("lastFilled") if isinstance(med, dict) else None,
                    category=info["category"],
                    hold_days_preop=info["hold_days"],
                    bridging_required=info.get("bridging", False),
                    reversal_agent=info.get("reversal")
                ))
                break
    
    return results


def parse_renal_function(labs: List[Any]) -> Optional[RenalFunction]:
    """Extract renal function from lab results."""
    renal = RenalFunction()
    
    for lab in labs:
        lab_str = str(lab).lower() if lab else ""
        
        if isinstance(lab, dict):
            name = (lab.get("name") or lab.get("testName") or "").lower()
            value = lab.get("value") or lab.get("result")
            date = lab.get("date") or lab.get("resultDate")
            
            try:
                if "creatinine" in name and "clearance" not in name:
                    renal.creatinine = float(re.sub(r'[^\d.]', '', str(value)))
                    renal.creatinine_date = date
                elif "egfr" in name or "gfr" in name:
                    renal.egfr = float(re.sub(r'[^\d.]', '', str(value)))
                    renal.egfr_date = date
                elif "bun" in name or "urea nitrogen" in name:
                    renal.bun = float(re.sub(r'[^\d.]', '', str(value)))
            except (ValueError, TypeError):
                continue
    
    # Determine contrast risk
    if renal.egfr:
        if renal.egfr >= 60:
            renal.contrast_risk = "low"
        elif renal.egfr >= 45:
            renal.contrast_risk = "moderate"
        elif renal.egfr >= 30:
            renal.contrast_risk = "high"
        else:
            renal.contrast_risk = "contraindicated"
    elif renal.creatinine:
        if renal.creatinine <= 1.2:
            renal.contrast_risk = "low"
        elif renal.creatinine <= 1.5:
            renal.contrast_risk = "moderate"
        elif renal.creatinine <= 2.0:
            renal.contrast_risk = "high"
        else:
            renal.contrast_risk = "contraindicated"
    
    return renal if renal.creatinine or renal.egfr else None


def parse_coagulation(labs: List[Any]) -> Optional[CoagulationPanel]:
    """Extract coagulation panel from lab results."""
    coag = CoagulationPanel()
    
    for lab in labs:
        if isinstance(lab, dict):
            name = (lab.get("name") or lab.get("testName") or "").lower()
            value = lab.get("value") or lab.get("result")
            date = lab.get("date") or lab.get("resultDate")
            
            try:
                if "inr" in name:
                    coag.inr = float(re.sub(r'[^\d.]', '', str(value)))
                    coag.pt_date = date
                elif name.startswith("pt") or "prothrombin" in name:
                    coag.pt = float(re.sub(r'[^\d.]', '', str(value)))
                    coag.pt_date = date
                elif "ptt" in name or "aptt" in name:
                    coag.ptt = float(re.sub(r'[^\d.]', '', str(value)))
            except (ValueError, TypeError):
                continue
    
    # Check if INR is in therapeutic range (for warfarin patients)
    if coag.inr:
        coag.therapeutic_range = 2.0 <= coag.inr <= 3.0
        coag.reversal_needed = coag.inr > 1.5
    
    return coag if coag.pt or coag.inr or coag.ptt else None


def parse_cardiac_clearance(documents: List[Any], notes: List[Any] = None) -> Optional[CardiacClearance]:
    """Extract cardiac clearance information from documents and notes."""
    cardiac = CardiacClearance()
    
    all_docs = (documents or []) + (notes or [])
    
    for doc in all_docs:
        doc_str = str(doc).lower() if doc else ""
        
        # Look for EF
        ef_match = re.search(r'(?:ef|ejection fraction)[:\s]*(\d+)[%\s]', doc_str)
        if ef_match:
            cardiac.ejection_fraction = float(ef_match.group(1))
        
        # Look for stress test
        if "stress test" in doc_str or "nuclear stress" in doc_str:
            if isinstance(doc, dict):
                cardiac.stress_test_date = doc.get("date")
            if "negative" in doc_str or "normal" in doc_str:
                cardiac.stress_test_result = "Negative"
            elif "positive" in doc_str or "abnormal" in doc_str:
                cardiac.stress_test_result = "Positive"
        
        # Look for clearance
        if "cleared" in doc_str or "clearance" in doc_str:
            if "not cleared" in doc_str or "deferred" in doc_str:
                cardiac.cleared = False
            else:
                cardiac.cleared = True
                if isinstance(doc, dict):
                    cardiac.clearance_date = doc.get("date")
    
    return cardiac if any([cardiac.cleared is not None, cardiac.ejection_fraction, 
                          cardiac.stress_test_date]) else None


def parse_critical_allergies(allergies: List[Any]) -> List[CriticalAllergy]:
    """Extract surgically relevant allergies."""
    results = []
    
    for allergy in allergies:
        allergy_str = str(allergy).lower() if allergy else ""
        
        allergen = ""
        reaction = None
        severity = "unknown"
        implication = None
        
        if isinstance(allergy, dict):
            allergen = (allergy.get("allergen") or allergy.get("name") or 
                       allergy.get("substance") or "").lower()
            reaction = allergy.get("reaction") or allergy.get("manifestation")
            severity = allergy.get("severity", "unknown")
        else:
            allergen = allergy_str
        
        # Check for contrast allergies
        for contrast in CONTRAST_ALLERGIES:
            if contrast in allergen:
                results.append(CriticalAllergy(
                    allergen=allergen.title(),
                    reaction=reaction,
                    severity=severity,
                    surgical_implication="Pre-medicate with steroids/antihistamines or use CO2/gadolinium"
                ))
                break
        
        # Check for surgical allergies
        for surgical in SURGICAL_ALLERGIES:
            if surgical in allergen:
                impl = {
                    "latex": "Use latex-free equipment",
                    "heparin": "Use alternative anticoagulation (bivalirudin)",
                    "protamine": "Cannot reverse heparin with protamine",
                    "chlorhexidine": "Use alternative skin prep"
                }.get(surgical)
                
                results.append(CriticalAllergy(
                    allergen=allergen.title(),
                    reaction=reaction,
                    severity=severity,
                    surgical_implication=impl
                ))
                break
    
    return results


def parse_vascular_history(procedures: List[Any], notes: List[Any] = None, problems: List[Any] = None) -> List[VascularHistory]:
    """Extract previous vascular interventions and diagnoses."""
    results = []

    vascular_keywords = [
        "angioplasty", "stent", "bypass", "endarterectomy", "embolectomy",
        "thrombectomy", "evar", "tevar", "fenestrated", "carotid", "aortic",
        "fem-pop", "femoral", "popliteal", "tibial", "iliac", "renal artery",
        "mesenteric", "subclavian", "av fistula", "av graft", "dialysis access",
        # Also include vascular diagnoses from problems
        "atherosclerosis", "peripheral vascular", "pvd", "pad", "stenosis",
        "aneurysm", "dissection", "occlusion", "claudication", "ischemia",
        "cerebrovascular", "stroke", "tia"
    ]

    all_items = (procedures or []) + (notes or []) + (problems or [])
    
    for item in all_items:
        item_str = str(item).lower() if item else ""
        
        for keyword in vascular_keywords:
            if keyword in item_str:
                proc_name = ""
                date = None
                location = None
                
                if isinstance(item, dict):
                    proc_name = item.get("name") or item.get("procedure") or item.get("description") or item.get("display") or item.get("title") or ""
                    date = item.get("date") or item.get("procedureDate") or item.get("onsetDateTime")
                    location = item.get("location") or item.get("site")
                else:
                    proc_name = str(item)
                
                results.append(VascularHistory(
                    procedure=proc_name,
                    date=date,
                    location=location
                ))
                break
    
    return results


def parse_diagnoses(problems: List[Any]) -> List[Diagnosis]:
    """Extract all diagnoses/problems with ICD-10 codes."""
    results = []

    for prob in problems:
        if not prob:
            continue

        # Handle various data structures
        if isinstance(prob, dict):
            # Try multiple possible field names for the diagnosis name
            name = (prob.get("description") or prob.get("name") or
                    prob.get("display") or prob.get("display_name") or
                    prob.get("problemName") or prob.get("conditionName") or
                    prob.get("diagnosisName") or "Unknown")

            # Try multiple possible field names for ICD-10 code
            # Handles both camelCase and snake_case variants
            icd10 = (prob.get("icd10_code") or prob.get("icd10Code") or
                     prob.get("icd10") or prob.get("code") or
                     prob.get("diagnosisCode") or prob.get("snomedCode") or
                     prob.get("snomed_code") or None)

            # Try to get status (both camelCase and snake_case)
            status = (prob.get("clinical_status") or prob.get("clinicalStatus") or
                      prob.get("status") or prob.get("problemStatus") or "active")

            # Try to get onset date (both camelCase and snake_case)
            onset = (prob.get("onset_date") or prob.get("onsetDate") or
                     prob.get("startDate") or prob.get("start_date") or
                     prob.get("dateOfOnset") or prob.get("diagnosedDate") or None)
        elif isinstance(prob, str):
            name = prob
            icd10 = None
            status = "active"
            onset = None
        else:
            continue

        # Skip empty names
        if not name or name == "Unknown":
            continue

        results.append(Diagnosis(
            name=str(name),
            icd10_code=str(icd10) if icd10 else None,
            status=str(status).lower(),
            onset_date=str(onset) if onset else None
        ))

    return results


def load_raw_events_for_patient(patient_id: str, data_dir: str = "data") -> List[Dict]:
    """
    Load raw events from JSONL file for a specific patient.
    Returns list of event payloads.
    """
    import os
    events = []
    jsonl_path = os.path.join(data_dir, "raw_events.jsonl")

    if not os.path.exists(jsonl_path):
        logger.warning(f"[IMAGING] Raw events file not found: {jsonl_path}")
        return events

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if str(event.get("patient_id", "")) == str(patient_id):
                        payload = event.get("payload")
                        if payload:
                            events.append(payload)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"[IMAGING] Error reading raw events: {e}")

    logger.info(f"[IMAGING] Loaded {len(events)} raw events for patient {patient_id}")
    return events


def extract_medications_from_raw_events(patient_id: str) -> List[Dict]:
    """
    Extract medications from raw events file for a patient.
    Returns list of medication dicts suitable for parse_antithrombotics.
    """
    import os
    medications = []
    seen_meds = set()
    jsonl_path = os.path.join("data", "raw_events.jsonl")

    if not os.path.exists(jsonl_path):
        return medications

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if patient_id not in line:
                    continue
                try:
                    event = json.loads(line.strip())
                    if str(event.get("patient_id", "")) != str(patient_id):
                        continue

                    payload = event.get("payload", {})

                    # Look for medications in various locations
                    for key in ['medications', 'active_medications', 'Medications']:
                        meds = payload.get(key)
                        if meds:
                            if isinstance(meds, dict):
                                meds = meds.get('Medications', []) or meds.get('medications', [])
                            if isinstance(meds, list):
                                for med in meds:
                                    if isinstance(med, dict):
                                        name = med.get('name') or med.get('medicationName') or med.get('drugName', '')
                                    else:
                                        name = str(med)
                                    if name and name.lower() not in seen_meds:
                                        seen_meds.add(name.lower())
                                        medications.append({'name': name})

                    # Also check raw text for medication mentions
                    raw_str = json.dumps(payload).lower()
                    for drug in ANTITHROMBOTIC_DRUGS.keys():
                        if drug in raw_str and drug not in seen_meds:
                            seen_meds.add(drug)
                            medications.append({'name': drug.title()})

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"[MEDS] Error reading raw events: {e}")

    if medications:
        logger.info(f"[MEDS] Extracted {len(medications)} medications from raw events")
    return medications


def extract_diagnoses_from_raw_events(patient_id: str) -> List[Dict]:
    """
    Extract diagnoses/problems from raw events file for a patient.
    Returns list of diagnosis dicts suitable for parse_diagnoses.

    Handles Athena's nested structure:
    - active_problems.Problems[].PatientSnomedICD10s[].DIAGNOSISCODE
    """
    import os
    diagnoses = []
    seen_names = set()
    jsonl_path = os.path.join("data", "raw_events.jsonl")

    if not os.path.exists(jsonl_path):
        return diagnoses

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if patient_id not in line:
                    continue
                try:
                    event = json.loads(line.strip())
                    if str(event.get("patient_id", "")) != str(patient_id):
                        continue

                    payload = event.get("payload", {})

                    # Look for problems in various locations
                    for key in ['problems', 'active_problems', 'diagnoses', 'Problems', 'chart_overview_problems']:
                        probs = payload.get(key)
                        if probs:
                            # Handle Athena's nested structure: active_problems.Problems[]
                            if isinstance(probs, dict):
                                probs = probs.get('Problems', []) or probs.get('problems', []) or [probs]
                            if isinstance(probs, list):
                                for prob in probs:
                                    if isinstance(prob, dict):
                                        # Extract problem name from various fields
                                        name = (prob.get('Name') or prob.get('name') or
                                               prob.get('description') or prob.get('problemName') or
                                               prob.get('ProblemName') or '')

                                        # Extract ICD-10 from Athena's nested PatientSnomedICD10s structure
                                        icd10 = None
                                        icd10_list = prob.get('PatientSnomedICD10s', [])
                                        if icd10_list and isinstance(icd10_list, list):
                                            for icd in icd10_list:
                                                if isinstance(icd, dict):
                                                    # Get the formatted ICD-10 code (I70.245)
                                                    icd10 = icd.get('UNSTRIPPEDDIAGNOSISCODE') or icd.get('DIAGNOSISCODE')
                                                    if icd10:
                                                        break

                                        # Fallback to flat fields
                                        if not icd10:
                                            icd10 = prob.get('icd10_code') or prob.get('icdCode') or prob.get('code')

                                        status = prob.get('status', 'active')

                                        if name and name.lower() not in seen_names:
                                            seen_names.add(name.lower())
                                            diagnoses.append({
                                                'name': name,
                                                'icd10_code': icd10,
                                                'status': status
                                            })
                                    else:
                                        name = str(prob)
                                        if name and name.lower() not in seen_names:
                                            seen_names.add(name.lower())
                                            diagnoses.append({
                                                'name': name,
                                                'icd10_code': None,
                                                'status': 'active'
                                            })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"[DIAG] Error reading raw events: {e}")

    if diagnoses:
        logger.info(f"[DIAG] Extracted {len(diagnoses)} diagnoses from raw events")
    return diagnoses


def extract_allergies_from_raw_events(patient_id: str) -> List[Dict]:
    """
    Extract allergies from raw events file for a patient.
    Returns list of allergy dicts suitable for parse_critical_allergies.
    """
    import os
    allergies = []
    seen_allergens = set()
    jsonl_path = os.path.join("data", "raw_events.jsonl")

    if not os.path.exists(jsonl_path):
        return allergies

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if patient_id not in line:
                    continue
                try:
                    event = json.loads(line.strip())
                    if str(event.get("patient_id", "")) != str(patient_id):
                        continue

                    payload = event.get("payload", {})

                    # Look for allergies in various locations
                    for key in ['allergies', 'Allergies', 'allergy']:
                        allergy_list = payload.get(key)
                        if allergy_list:
                            if isinstance(allergy_list, dict):
                                allergy_list = allergy_list.get('Allergies', []) or allergy_list.get('allergies', [])
                            if isinstance(allergy_list, list):
                                for allergy in allergy_list:
                                    if isinstance(allergy, dict):
                                        allergen = allergy.get('allergen') or allergy.get('name') or allergy.get('description', '')
                                        reaction = allergy.get('reaction') or allergy.get('reactionType', '')
                                    else:
                                        allergen = str(allergy)
                                        reaction = ''
                                    if allergen and allergen.lower() not in seen_allergens:
                                        seen_allergens.add(allergen.lower())
                                        allergies.append({
                                            'allergen': allergen,
                                            'reaction': reaction
                                        })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"[ALLERGY] Error reading raw events: {e}")

    if allergies:
        logger.info(f"[ALLERGY] Extracted {len(allergies)} allergies from raw events")
    return allergies


def extract_embedded_imaging(raw_data: Dict[str, Any], patient_id: str = None) -> List[Document]:
    """
    Extract imaging findings embedded in clinical notes/text.
    Finds references to duplex, ABIs, vein mapping, CTAs etc. in free text.

    If patient_id is provided, also searches raw events file for additional imaging data.
    """
    results = []

    # Patterns for embedded imaging data
    # Note: Handle HTML entities like &#39; for apostrophe
    patterns = {
        # Match "abi's (R) 0.39" or "(L) 0.24" format
        'abi': r'\(?([RL])\)?\s*[\d\.]+',
        'abi_context': r'abi[&#39;\'s]*.*?\(([RL])\)\s*([\d\.]+)',
        'duplex': r'((?:le|lower extremity|carotid|aorta|renal|arterial)?[^.]*duplex[^.]{0,150})',
        'vein_mapping': r'(vein mapping[^.]{0,100})',
        'cta': r'(\bcta\b[^.]{0,100})',
        'angiogram': r'(angiogram[^.]{0,100})',
    }

    # Build searchable text more efficiently
    text_parts = []

    # Add raw_data
    if raw_data:
        text_parts.append(json.dumps(raw_data))

    # Load and search raw events if patient_id provided
    # Only load relevant payloads to avoid memory issues
    if patient_id:
        import os
        jsonl_path = os.path.join("data", "raw_events.jsonl")
        if os.path.exists(jsonl_path):
            event_count = 0
            max_events = 50  # Limit to prevent slowdown
            try:
                with open(jsonl_path, "r") as f:
                    for line in f:
                        if event_count >= max_events:
                            break
                        # Quick pre-check before parsing JSON
                        if patient_id not in line:
                            continue
                        try:
                            event = json.loads(line.strip())
                            if str(event.get("patient_id", "")) == str(patient_id):
                                event_count += 1
                                payload = event.get("payload")
                                if payload and isinstance(payload, dict):
                                    # Only stringify relevant fields containing clinical data
                                    for key in ['historical_clinical_encounters', 'notes', 'raw', 'surgical', 'summary', 'diagnoses', 'assessment_plan']:
                                        if key in payload:
                                            text_parts.append(json.dumps(payload[key]))
                        except:
                            continue
            except Exception as e:
                logger.error(f"[IMAGING] Error reading raw events: {e}")

    # Join and lowercase for searching
    raw_str = ' '.join(text_parts).replace('\\n', ' ').replace('\\r', ' ')
    raw_lower = raw_str.lower()

    # Extract ABI values - look for pattern like "abi's (R) 0.39 and (L) 0.24"
    abi_values = {}

    # Look for (R) value and (L) value patterns when "abi" is present
    if 'abi' in raw_lower:
        # Find all (R) or (L) followed immediately by a decimal value (like "(R) 0.39")
        # The decimal must start with a digit, not a letter
        side_value_pattern = r'\(([rl])\)\s*(\d+\.?\d*)'
        all_matches = re.findall(side_value_pattern, raw_lower)
        for match in all_matches:
            side, value = match
            side_name = 'Right' if side.upper() == 'R' else 'Left'
            try:
                val = float(value)
                if 0.1 <= val <= 1.5:  # Valid ABI range
                    abi_values[side_name] = value
            except:
                pass

    if abi_values:
        # Find date context - look for "done MM/DD/YYYY" pattern
        date_match = re.search(r'(?:done|dated?)\s*(\d{1,2}/\d{1,2}/\d{4})', raw_lower)
        date = date_match.group(1) if date_match else None

        abi_text = ', '.join([f"{k}: {v}" for k, v in abi_values.items()])
        results.append(Document(
            id=f"abi-{uuid.uuid4().hex[:8]}",
            title=f"Ankle-Brachial Index: {abi_text}",
            category="Ultrasound",
            date=date,
            author=None,
            url=None
        ))

    # Extract duplex findings
    duplex_matches = re.findall(patterns['duplex'], raw_lower, re.IGNORECASE)
    seen_duplex = set()
    for match in duplex_matches:
        # Clean up the match
        cleaned = re.sub(r'<[^>]+>', '', match).strip()
        cleaned = re.sub(r'&#39;', "'", cleaned)
        if len(cleaned) > 20 and cleaned[:50] not in seen_duplex:
            seen_duplex.add(cleaned[:50])
            # Try to extract date
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cleaned)
            date = date_match.group(1) if date_match else None

            # Determine type
            title = "Arterial Duplex Study"
            if "vein" in cleaned:
                title = "Venous Duplex Study"
            elif "carotid" in cleaned:
                title = "Carotid Duplex Study"
            elif "aorta" in cleaned:
                title = "Aorta Duplex Study"

            results.append(Document(
                id=f"duplex-{uuid.uuid4().hex[:8]}",
                title=f"{title}: {cleaned[:80]}...",
                category="Ultrasound",
                date=date,
                author=None,
                url=None
            ))

    # Extract vein mapping
    vein_matches = re.findall(patterns['vein_mapping'], raw_lower, re.IGNORECASE)
    for match in vein_matches:
        cleaned = re.sub(r'<[^>]+>', '', match).strip()
        if len(cleaned) > 10:
            date_match = re.search(r'(\d{1,2}/\d{1,2})', cleaned)
            date = date_match.group(1) if date_match else None

            results.append(Document(
                id=f"veinmap-{uuid.uuid4().hex[:8]}",
                title=f"Vein Mapping: {cleaned[:60]}",
                category="Ultrasound",
                date=date,
                author=None,
                url=None
            ))

    return results


def parse_documents(documents: List[Any], notes: List[Any] = None) -> List[Document]:
    """Extract and categorize clinical documents."""
    results = []
    seen_ids = set()

    # Document type categorization keywords
    IMAGING_CTA = ["cta", "ct angio", "ct angiogram", "computed tomography angio"]
    IMAGING_CT_MRI = ["ct ", "mri", "magnetic resonance", "computed tomography"]
    ULTRASOUND = ["ultrasound", "duplex", "doppler", "sonograph", "us ", "u/s"]
    OPERATIVE = ["operative", "surgical", "procedure note", "op note", "surgery"]
    PATHOLOGY = ["pathology", "pathologic", "biopsy", "cytology", "histology"]
    LAB = ["lab", "laboratory", "result", "blood", "chemistry", "hematology"]

    all_docs = (documents or []) + (notes or [])

    for doc in all_docs:
        if not doc or not isinstance(doc, dict):
            continue

        # Extract document ID
        doc_id = str(doc.get("id") or doc.get("documentId") or doc.get("noteId") or "")
        if not doc_id or doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)

        # Extract title
        title = (doc.get("title") or doc.get("description") or
                 doc.get("documentName") or doc.get("noteType") or "Untitled")

        # Extract date and author
        date = doc.get("date") or doc.get("documentDate") or doc.get("createdDate")
        author = doc.get("author") or doc.get("provider") or doc.get("createdBy")
        url = doc.get("url") or doc.get("link") or None

        # Categorize by title/type
        title_lower = str(title).lower()
        category = "Other"

        if any(kw in title_lower for kw in IMAGING_CTA):
            category = "CTA"
        elif any(kw in title_lower for kw in ULTRASOUND):
            category = "Ultrasound"
        elif any(kw in title_lower for kw in IMAGING_CT_MRI):
            category = "CT/MRI"
        elif any(kw in title_lower for kw in OPERATIVE):
            category = "Operative"
        elif any(kw in title_lower for kw in PATHOLOGY):
            category = "Pathology"
        elif any(kw in title_lower for kw in LAB):
            category = "Lab"
        else:
            category = "Note"

        results.append(Document(
            id=doc_id,
            title=str(title),
            category=category,
            date=str(date) if date else None,
            author=str(author) if author else None,
            url=str(url) if url else None
        ))

    return results


def _extract_name_fallback(raw_data: Dict[str, Any], patient_id: str) -> str:
    """
    Extract patient name with multiple fallback strategies.
    Searches through various data structures to find patient name.
    """
    # Try standard patient/demographics fields first
    patient_info = (raw_data.get("demographics") or {}).get("data") or {}
    name = patient_info.get("name") or patient_info.get("patientName")
    if name:
        if isinstance(name, dict):
            return name.get("full") or f"{name.get('given', [''])[0]} {name.get('family', '')}".strip()
        return str(name)

    # Try patient field directly
    patient_field = raw_data.get("patient") or {}
    if isinstance(patient_field, dict):
        first = patient_field.get("FirstName") or patient_field.get("first_name") or ""
        last = patient_field.get("LastName") or patient_field.get("last_name") or ""
        if first or last:
            return f"{first} {last}".strip()

    # Search unknown array for patient data
    unknown_items = raw_data.get("unknown") or []
    for item in unknown_items:
        if isinstance(item, dict):
            data = item.get("data", {})
            if isinstance(data, dict):
                # Check for patient object inside data
                patient_obj = data.get("patient")
                if isinstance(patient_obj, dict):
                    first = patient_obj.get("FirstName") or patient_obj.get("first_name") or ""
                    last = patient_obj.get("LastName") or patient_obj.get("last_name") or ""
                    if first or last:
                        return f"{first} {last}".strip()

    return "Unknown"


# ============================================================
# MAIN PARSER
# ============================================================

def build_vascular_profile(patient_id: str, raw_data: Dict[str, Any]) -> VascularProfile:
    """Build a complete vascular surgery profile from raw EHR data."""

    logger.info(f"Building vascular profile for patient {patient_id}")

    # Extract patient identifiers
    # Use (x or {}) pattern to handle explicit None values
    patient_info = (raw_data.get("demographics") or {}).get("data") or {}
    mrn = patient_info.get("mrn") or patient_info.get("patientId") or patient_id

    # Use fallback name extraction for robustness
    name = _extract_name_fallback(raw_data, patient_id)

    # Parse medications
    meds_data = (raw_data.get("medications") or {}).get("data") or []
    if isinstance(meds_data, dict):
        meds_data = meds_data.get("medications", [])

    # Fallback: extract medications from raw events file if no structured data
    if not meds_data and patient_id:
        meds_data = extract_medications_from_raw_events(patient_id)

    antithrombotics = parse_antithrombotics(meds_data)

    # Parse labs
    labs_data = (raw_data.get("labs") or {}).get("data") or []
    if isinstance(labs_data, dict):
        labs_data = labs_data.get("results", []) or labs_data.get("labs", [])
    renal = parse_renal_function(labs_data)
    coag = parse_coagulation(labs_data)

    # Parse documents/notes
    docs_data = (raw_data.get("documents") or {}).get("data") or []
    notes_data = (raw_data.get("notes") or {}).get("data") or []
    cardiac = parse_cardiac_clearance(docs_data, notes_data)

    # Parse and categorize all clinical documents
    documents = parse_documents(docs_data, notes_data)

    # Also extract embedded imaging findings from clinical notes
    # Pass patient_id to also search raw events file
    embedded_imaging = extract_embedded_imaging(raw_data, patient_id=patient_id)
    if embedded_imaging:
        logger.info(f"Found {len(embedded_imaging)} embedded imaging findings")
        documents.extend(embedded_imaging)

    logger.info(f"Parsed {len(documents)} total clinical documents (including embedded imaging)")

    # Parse allergies
    allergy_data = (raw_data.get("allergies") or {}).get("data") or []
    if isinstance(allergy_data, dict):
        allergy_data = allergy_data.get("allergies", [])

    # Fallback: extract allergies from raw events file if no structured data
    if not allergy_data and patient_id:
        allergy_data = extract_allergies_from_raw_events(patient_id)

    allergies = parse_critical_allergies(allergy_data)

    # Parse procedures and problems for vascular history
    proc_data = (raw_data.get("procedures") or {}).get("data") or []
    problems_data = (raw_data.get("problems") or {}).get("data") or []
    if isinstance(problems_data, dict):
        problems_data = problems_data.get("problems", []) or problems_data.get("activeProblems", [])

    # Fallback: extract diagnoses from raw events file if no structured data
    if not problems_data and patient_id:
        problems_data = extract_diagnoses_from_raw_events(patient_id)

    # Include problems as potential vascular diagnoses
    history = parse_vascular_history(proc_data, notes_data, problems_data)

    # Parse ALL diagnoses/problems (not just vascular-related)
    diagnoses = parse_diagnoses(problems_data)
    logger.info(f"Parsed {len(diagnoses)} diagnoses from problems data")
    
    # Determine risk flags (ensure bool, not None)
    high_bleeding_risk = bool(
        len([a for a in antithrombotics if a.category in ["vka", "doac"]]) > 0 or
        (coag and coag.inr and coag.inr > 1.5)
    )

    contrast_caution = bool(
        (renal and renal.contrast_risk in ["moderate", "high", "contraindicated"]) or
        any("contrast" in a.allergen.lower() for a in allergies)
    )
    
    cardiac_risk = "unknown"
    if cardiac:
        if cardiac.cleared:
            cardiac_risk = "cleared"
        elif cardiac.ejection_fraction:
            if cardiac.ejection_fraction >= 55:
                cardiac_risk = "low"
            elif cardiac.ejection_fraction >= 40:
                cardiac_risk = "moderate"
            else:
                cardiac_risk = "high"
    
    profile = VascularProfile(
        patient_id=patient_id,
        mrn=str(mrn),
        name=str(name),
        antithrombotics=antithrombotics,
        renal_function=renal,
        coagulation=coag,
        cardiac_clearance=cardiac,
        critical_allergies=allergies,
        diagnoses=diagnoses,
        documents=documents,
        vascular_history=history,
        high_bleeding_risk=high_bleeding_risk,
        contrast_caution=contrast_caution,
        cardiac_risk=cardiac_risk
    )

    logger.info(f"Vascular profile built: {len(antithrombotics)} antithrombotics, "
                f"{len(allergies)} critical allergies, {len(history)} prior procedures, "
                f"{len(diagnoses)} diagnoses, {len(documents)} documents")
    
    return profile