"""
Vascular Surgery Data Parser

Extracts surgery-relevant clinical data from raw EHR payloads.
Optimized for pre-op, intra-op, and post-op vascular surgery workflows.
"""

import re
import logging
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
    name = patient_info.get("name") or patient_info.get("patientName") or "Unknown"
    if isinstance(name, dict):
        name = name.get("full") or f"{name.get('given', [''])[0]} {name.get('family', '')}"

    # Parse medications
    meds_data = (raw_data.get("medications") or {}).get("data") or []
    if isinstance(meds_data, dict):
        meds_data = meds_data.get("medications", [])
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

    # Parse allergies
    allergy_data = (raw_data.get("allergies") or {}).get("data") or []
    if isinstance(allergy_data, dict):
        allergy_data = allergy_data.get("allergies", [])
    allergies = parse_critical_allergies(allergy_data)

    # Parse procedures and problems for vascular history
    proc_data = (raw_data.get("procedures") or {}).get("data") or []
    problems_data = (raw_data.get("problems") or {}).get("data") or []
    if isinstance(problems_data, dict):
        problems_data = problems_data.get("problems", []) or problems_data.get("activeProblems", [])
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
        vascular_history=history,
        high_bleeding_risk=high_bleeding_risk,
        contrast_caution=contrast_caution,
        cardiac_risk=cardiac_risk
    )

    logger.info(f"Vascular profile built: {len(antithrombotics)} antithrombotics, "
                f"{len(allergies)} critical allergies, {len(history)} prior procedures, "
                f"{len(diagnoses)} diagnoses")
    
    return profile