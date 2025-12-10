"""
Active Fetch API Routes

Handles active data extraction requests and vascular profile generation.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vascular_parser import build_vascular_profile, VascularProfile

logger = logging.getLogger("shadow-ehr")

router = APIRouter(prefix="/active", tags=["Active Fetch"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class ActiveFetchRequest(BaseModel):
    """Request to process active fetch data."""
    patient_id: str
    mrn: Optional[str] = None
    data: Dict[str, Any]
    fetch_type: str = "all"  # all, preop, intraop, postop


class VascularProfileResponse(BaseModel):
    """Vascular profile response."""
    success: bool
    profile: Optional[VascularProfile] = None
    error: Optional[str] = None
    timestamp: str


class PreOpChecklist(BaseModel):
    """Pre-operative checklist for vascular surgery."""
    patient_id: str
    mrn: str
    name: str
    
    # Medication status
    antithrombotics_held: bool = False
    anticoagulant_details: str = ""
    bridging_required: bool = False
    
    # Lab status
    renal_function_ok: bool = False
    renal_details: str = ""
    coagulation_ok: bool = False
    coagulation_details: str = ""
    
    # Cardiac status
    cardiac_cleared: bool = False
    cardiac_details: str = ""
    
    # Allergy alerts
    contrast_allergy: bool = False
    allergy_alerts: list = []
    
    # Overall readiness
    ready_for_surgery: bool = False
    blocking_issues: list = []


# ============================================================
# STORAGE
# ============================================================

# In-memory storage for active fetch results and profiles
active_fetch_cache: Dict[str, Dict] = {}
vascular_profiles: Dict[str, VascularProfile] = {}

# Reference to main patient cache (will be set by main.py)
main_patient_cache: Dict[str, Dict] = {}

def set_main_cache(cache: Dict):
    """Allow main.py to share its patient cache."""
    global main_patient_cache
    main_patient_cache = cache


def transform_cache_to_vascular_format(patient_id: str, cache_data: Dict) -> Dict:
    """
    Transform main.py cache format to the format expected by build_vascular_profile.

    Input format (from main.py):
        {'patient': {...}, 'vitals': {...}, 'medications': [...], 'problems': [...]}

    Output format (for vascular_parser):
        {'demographics': {'data': {...}}, 'medications': {'data': [...]}, ...}
    """
    return {
        "demographics": {"data": cache_data.get("patient") or {}},
        "vitals": {"data": cache_data.get("vitals") or {}},
        "medications": {"data": cache_data.get("medications") or []},
        "problems": {"data": cache_data.get("problems") or []},
        "labs": {"data": cache_data.get("labs") or []},
        "allergies": {"data": cache_data.get("allergy") or cache_data.get("allergies") or []},
        "documents": {"data": cache_data.get("documents") or []},
        "notes": {"data": cache_data.get("notes") or cache_data.get("note") or []},
        "procedures": {"data": cache_data.get("procedures") or []},
    }


# ============================================================
# ROUTES
# ============================================================

@router.post("/ingest")
async def ingest_active_fetch(request: ActiveFetchRequest):
    """
    Process data from an active fetch operation.
    Generates vascular profile and caches results.
    """
    logger.info(f"Active fetch ingest: patient={request.patient_id}, type={request.fetch_type}")
    
    try:
        # Cache raw data
        active_fetch_cache[request.patient_id] = {
            "data": request.data,
            "fetch_type": request.fetch_type,
            "timestamp": datetime.now().isoformat()
        }
        
        # Build vascular profile
        profile = build_vascular_profile(request.patient_id, request.data)
        vascular_profiles[request.patient_id] = profile
        
        logger.info(f"Vascular profile generated for {request.patient_id}")
        
        return {
            "success": True,
            "patient_id": request.patient_id,
            "profile_generated": True,
            "antithrombotics_found": len(profile.antithrombotics),
            "critical_allergies": len(profile.critical_allergies),
            "prior_procedures": len(profile.vascular_history)
        }
        
    except Exception as e:
        logger.error(f"Error processing active fetch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{patient_id}", response_model=VascularProfileResponse)
async def get_vascular_profile(patient_id: str):
    """Get the vascular surgery profile for a patient."""

    # First check vascular profiles (from active fetch)
    if patient_id in vascular_profiles:
        return VascularProfileResponse(
            success=True,
            profile=vascular_profiles[patient_id],
            timestamp=datetime.now().isoformat()
        )

    # Fallback: check main patient cache and build profile on-the-fly
    if patient_id in main_patient_cache:
        logger.info(f"Building vascular profile from main cache for {patient_id}")
        cache_data = main_patient_cache[patient_id]

        # Transform to vascular parser format and build profile
        transformed_data = transform_cache_to_vascular_format(patient_id, cache_data)
        profile = build_vascular_profile(patient_id, transformed_data)
        vascular_profiles[patient_id] = profile  # Cache for future requests

        return VascularProfileResponse(
            success=True,
            profile=profile,
            timestamp=datetime.now().isoformat()
        )

    return VascularProfileResponse(
        success=False,
        error="Profile not found. Navigate to patient chart in Athena first.",
        timestamp=datetime.now().isoformat()
    )


@router.get("/preop-checklist/{patient_id}")
async def get_preop_checklist(patient_id: str) -> PreOpChecklist:
    """
    Generate a pre-operative checklist for vascular surgery.
    """
    # Check if profile exists, if not try to build from main cache
    if patient_id not in vascular_profiles:
        if patient_id in main_patient_cache:
            logger.info(f"Building vascular profile from main cache for preop checklist: {patient_id}")
            cache_data = main_patient_cache[patient_id]
            transformed_data = transform_cache_to_vascular_format(patient_id, cache_data)
            profile = build_vascular_profile(patient_id, transformed_data)
            vascular_profiles[patient_id] = profile
        else:
            raise HTTPException(status_code=404, detail="Profile not found. Navigate to patient chart in Athena first.")
    
    profile = vascular_profiles[patient_id]
    blocking_issues = []
    
    # Analyze antithrombotics
    anticoag_on = [a for a in profile.antithrombotics if a.category in ["vka", "doac", "injectable"]]
    antiplatelet_on = [a for a in profile.antithrombotics if a.category == "antiplatelet"]
    
    anticoag_details = ""
    bridging = False
    if anticoag_on:
        meds = ", ".join([f"{a.name} (hold {a.hold_days_preop}d)" for a in anticoag_on])
        anticoag_details = f"Active: {meds}"
        bridging = any(a.bridging_required for a in anticoag_on)
        if any(a.hold_days_preop > 0 for a in anticoag_on):
            blocking_issues.append(f"Anticoagulants need to be held")
    
    # Analyze renal function
    renal_ok = True
    renal_details = "Not available"
    if profile.renal_function:
        rf = profile.renal_function
        if rf.egfr:
            renal_details = f"eGFR: {rf.egfr} ({rf.contrast_risk} contrast risk)"
            renal_ok = rf.contrast_risk in ["low", "moderate"]
        elif rf.creatinine:
            renal_details = f"Cr: {rf.creatinine} ({rf.contrast_risk} contrast risk)"
            renal_ok = rf.contrast_risk in ["low", "moderate"]
        
        if not renal_ok:
            blocking_issues.append("High contrast risk - consider alternatives")
    
    # Analyze coagulation
    coag_ok = True
    coag_details = "Not available"
    if profile.coagulation:
        coag = profile.coagulation
        if coag.inr:
            coag_details = f"INR: {coag.inr}"
            if coag.inr > 1.5:
                coag_ok = False
                blocking_issues.append(f"INR elevated ({coag.inr}) - needs reversal")
    
    # Analyze cardiac clearance
    cardiac_ok = profile.cardiac_risk in ["cleared", "low"]
    cardiac_details = "Not documented"
    if profile.cardiac_clearance:
        cc = profile.cardiac_clearance
        if cc.cleared is not None:
            cardiac_details = "Cleared" if cc.cleared else "NOT cleared"
            cardiac_ok = cc.cleared
        if cc.ejection_fraction:
            cardiac_details += f", EF {cc.ejection_fraction}%"
        if not cardiac_ok and cc.cleared is False:
            blocking_issues.append("Cardiac clearance pending")
    
    # Analyze allergies
    contrast_allergy = any("contrast" in a.allergen.lower() or "iodine" in a.allergen.lower() 
                         for a in profile.critical_allergies)
    allergy_alerts = [f"{a.allergen}: {a.surgical_implication}" 
                     for a in profile.critical_allergies if a.surgical_implication]
    
    if contrast_allergy:
        blocking_issues.append("Contrast allergy - pre-medication required")
    
    # Determine overall readiness
    ready = len(blocking_issues) == 0
    
    return PreOpChecklist(
        patient_id=patient_id,
        mrn=profile.mrn,
        name=profile.name,
        antithrombotics_held=len(anticoag_on) == 0,
        anticoagulant_details=anticoag_details or "None active",
        bridging_required=bridging,
        renal_function_ok=renal_ok,
        renal_details=renal_details,
        coagulation_ok=coag_ok,
        coagulation_details=coag_details,
        cardiac_cleared=cardiac_ok,
        cardiac_details=cardiac_details,
        contrast_allergy=contrast_allergy,
        allergy_alerts=allergy_alerts,
        ready_for_surgery=ready,
        blocking_issues=blocking_issues
    )


@router.get("/intraop-summary/{patient_id}")
async def get_intraop_summary(patient_id: str):
    """
    Get intra-operative summary focusing on anatomy and history.
    """
    if patient_id not in vascular_profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile = vascular_profiles[patient_id]
    
    return {
        "patient_id": patient_id,
        "name": profile.name,
        "prior_interventions": [
            {
                "procedure": h.procedure,
                "date": h.date,
                "location": h.location,
                "details": h.details
            } for h in profile.vascular_history
        ],
        "critical_allergies": [
            {
                "allergen": a.allergen,
                "implication": a.surgical_implication
            } for a in profile.critical_allergies
        ],
        "contrast_caution": profile.contrast_caution,
        "high_bleeding_risk": profile.high_bleeding_risk
    }


@router.get("/postop-plan/{patient_id}")
async def get_postop_plan(patient_id: str):
    """
    Get post-operative planning summary.
    """
    if patient_id not in vascular_profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile = vascular_profiles[patient_id]
    
    # Generate anticoagulation resumption plan
    ac_plan = []
    for med in profile.antithrombotics:
        if med.category in ["vka", "doac"]:
            ac_plan.append({
                "medication": med.name,
                "dose": med.dose,
                "resume_timing": f"Resume {24 - med.hold_days_preop * 12}h post-op if hemostasis adequate"
            })
    
    return {
        "patient_id": patient_id,
        "name": profile.name,
        "anticoagulation_plan": ac_plan,
        "renal_monitoring": profile.contrast_caution,
        "bleeding_precautions": profile.high_bleeding_risk,
        "discharge_medications": [
            {"name": med.name, "dose": med.dose, "frequency": med.frequency}
            for med in profile.antithrombotics
        ]
    }


@router.get("/patients")
async def list_profiled_patients():
    """List all patients with generated vascular profiles."""
    return {
        "patients": [
            {
                "patient_id": pid,
                "mrn": profile.mrn,
                "name": profile.name,
                "last_updated": profile.last_updated,
                "risk_flags": {
                    "bleeding": profile.high_bleeding_risk,
                    "contrast": profile.contrast_caution,
                    "cardiac": profile.cardiac_risk
                }
            }
            for pid, profile in vascular_profiles.items()
        ],
        "count": len(vascular_profiles)
    }


@router.delete("/profile/{patient_id}")
async def clear_profile(patient_id: str):
    """Clear a patient's profile from cache."""
    removed = False
    if patient_id in vascular_profiles:
        del vascular_profiles[patient_id]
        removed = True
    if patient_id in active_fetch_cache:
        del active_fetch_cache[patient_id]
    
    return {"removed": removed, "patient_id": patient_id}