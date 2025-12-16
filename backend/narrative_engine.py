"""
Narrative Engine: The Cognitive Layer
Strictly separates Data Sorting from Narrative Generation.
"""

import os
import logging
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel

# Google GenAI
from google import genai
from google.genai import types

# The Data Separation Layer
from backend.vascular_parser import build_vascular_profile, VascularProfile
from backend.files import get_artifact_store

logger = logging.getLogger("shadow-ehr")

class NarrativeRequest(BaseModel):
    include_vision: bool = False
    # The engine now creates the narrative based on the specific "View" requested
    narrative_type: str = "vascular_intro" # vascular_intro, discharge_summary, etc.

class NarrativeResponse(BaseModel):
    narrative: str
    sources_used: List[str]
    data_quality_score: float # New: How much data did we actually have?
    generated_at: str

class NarrativeEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.model_id = "gemini-2.0-flash"
        else:
            self.client = None
            logger.warning("NarrativeEngine: No API Key found.")

    async def generate_narrative(self, patient_id: str, raw_cache_data: Dict[str, Any], include_vision: bool = False) -> NarrativeResponse:
        """
        1. ABSORB: Take raw cache.
        2. SORT: Run strict extractors (VascularProfile).
        3. SYNTHESIZE: Send *only* sorted data to LLM.
        """
        
        # --- STEP 1: THE DATA SEPARATION LAYER ---
        # We do not send raw_cache_data to the LLM. We build a Profile.
        logger.info(f"[NARRATIVE] 1. Sorting data for {patient_id}...")
        
        # Transform raw cache into the format vascular_parser expects
        # (This adapts the main.py cache structure to the parser's expected input)
        parser_input = {
            "demographics": {"data": raw_cache_data.get("patient") or {}},
            "medications": {"data": raw_cache_data.get("medications") or []},
            "problems": {"data": raw_cache_data.get("problems") or []},
            "labs": {"data": raw_cache_data.get("labs") or []},
            "notes": {"data": raw_cache_data.get("notes") or []},
            "procedures": {"data": raw_cache_data.get("surgical_history") or []},
            "allergies": {"data": raw_cache_data.get("allergies") or []},
            "documents": {"data": raw_cache_data.get("documents") or []}
        }

        # This function acts as the firewall/sorter
        profile: VascularProfile = build_vascular_profile(patient_id, parser_input)
        
        # --- STEP 2: VISION EXTRACTION (Optional) ---
        vision_insights = ""
        doc_sources = []
        if include_vision:
            logger.info("[NARRATIVE] 2. Absorbing visual artifacts...")
            vision_insights, doc_sources = await self._extract_from_documents(patient_id)

        # --- STEP 3: CONTEXT PREPARATION ---
        # We serialize the SORTED profile, not the raw JSON.
        llm_context = self._prepare_llm_context(profile, vision_insights)
        
        # Calculate a basic quality score based on fields present
        quality_score = self._calculate_data_quality(profile)

        # --- STEP 4: GENERATION ---
        if not self.client:
            return NarrativeResponse(narrative="AI Config Missing", sources_used=[], data_quality_score=0, generated_at="")

        logger.info("[NARRATIVE] 3. Generating Narrative...")
        prompt = f"""
        ROLE: Expert Vascular Surgeon's Scribe.
        TASK: Write the "History of Present Illness" (HPI) opening paragraph.
        
        INPUT DATA (Sorted & Verified):
        {llm_context}

        INSTRUCTIONS:
        1. Start EXACTLY with: "This is a [AGE] year-old [GENDER]..."
        2. List ONLY relevant comorbidities (HTN, HLD, DM, CAD, CKD, COPD, Smoking).
        3. Summarize Surgical History chronologically. If dates are known, use them. If not, say "history of...".
        4. Mention critical vascular medications (Antiplatelets/Anticoagulants) only if active.
        5. Incorporate insights extracted from documents if they add specific dates or procedures not in the structured data.
        6. Style: Professional, medical, concise. No bullet points. Max 4 sentences.

        OUTPUT:
        """

        try:
            # Use the new google-genai SDK API
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            narrative = response.text.strip()
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            narrative = "Could not generate narrative due to AI service error."

        return NarrativeResponse(
            narrative=narrative,
            sources_used=["Structured EHR Data"] + doc_sources,
            data_quality_score=quality_score,
            generated_at=datetime.now().isoformat()
        )

    def _prepare_llm_context(self, profile: VascularProfile, vision_text: str) -> str:
        """
        Converts the Pydantic VascularProfile into a clean text block.
        This is the only thing the LLM sees.
        """
        # Comorbidities Filter
        relevant_dx = [dx.name for dx in profile.diagnoses if dx.status == 'active']

        # Medications Filter (Antithrombotics only)
        meds = [f"{m.name} ({m.category})" for m in profile.antithrombotics]

        # Vascular-specific history
        vascular_hx = []
        for h in profile.vascular_history:
            if h.date:
                vascular_hx.append(f"{h.procedure} ({h.date})")
            else:
                vascular_hx.append(h.procedure)

        # All surgical history
        surgical_hx = []
        for h in profile.surgical_history:
            if h.date:
                surgical_hx.append(f"{h.procedure} ({h.date})")
            else:
                surgical_hx.append(h.procedure)

        # Format age/gender
        age_str = f"{profile.age}" if profile.age else "Unknown age"
        gender_str = profile.gender or "Unknown gender"

        context = f"""
        PATIENT: {profile.name}
        MRN: {profile.mrn}
        AGE: {age_str} years old
        GENDER: {gender_str}

        VERIFIED COMORBIDITIES:
        {', '.join(relevant_dx) if relevant_dx else "None documented"}

        ACTIVE ANTITHROMBOTICS:
        {', '.join(meds) if meds else "None"}

        VASCULAR SURGICAL HISTORY:
        {'; '.join(vascular_hx) if vascular_hx else "None documented"}

        ALL SURGICAL HISTORY:
        {'; '.join(surgical_hx) if surgical_hx else "None documented in structured data"}

        DOCUMENT EXTRACTIONS (Vision Model):
        {vision_text if vision_text else "No additional documents read."}
        """
        return context

    async def _extract_from_documents(self, patient_id: str) -> tuple[str, List[str]]:
        """
        Uses Vision to read documents. This constitutes 'reading' data 
        that wasn't in the structured API response.
        """
        store = get_artifact_store()
        artifacts = store.list_by_patient(patient_id)
        
        # Sort by date, take top 3
        # In a real system, we'd filter for 'Operative Note' types
        recent_artifacts = sorted(artifacts, key=lambda x: x.stored_at or "", reverse=True)[:3]
        
        extracted_info = []
        sources = []
        
        if not self.client:
            return "", []

        for art in recent_artifacts:
            # Only process images/PDFs
            if not art.mime_type or 'json' in art.mime_type: continue
            
            data = store.get(art.artifact_id)
            if not data: continue

            try:
                prompt = "Read this medical document. List any surgical procedures and their dates found in the text. Format: Procedure - Date."

                resp = await self.client.aio.models.generate_content(
                    model=self.model_id,
                    contents=[
                        types.Part.from_bytes(data=data, mime_type=art.mime_type),
                        prompt
                    ]
                )

                if resp.text:
                    extracted_info.append(f"[From {art.original_filename}]: {resp.text}")
                    sources.append(f"Doc: {art.original_filename}")
            except Exception as e:
                logger.error(f"Vision failed on {art.artifact_id}: {e}")

        return "\n".join(extracted_info), sources

    def _calculate_data_quality(self, profile: VascularProfile) -> float:
        """Simple heuristic for data completeness."""
        score = 0.0
        if profile.name != "Unknown": score += 0.2
        if profile.diagnoses: score += 0.3
        if profile.antithrombotics: score += 0.1
        if profile.vascular_history: score += 0.2
        if profile.renal_function: score += 0.1
        if profile.cardiac_clearance: score += 0.1
        return min(score, 1.0)

_narrative_engine = NarrativeEngine()
def get_narrative_engine():
    return _narrative_engine
