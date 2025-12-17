"""
Narrative Engine: The Cognitive Layer
Strictly separates Data Sorting from Narrative Generation.

Architecture:
1. ABSORB: Raw cache data comes in
2. SORT: VascularProfile extracts and types the data (the firewall)
3. SYNTHESIZE: LLM receives ONLY sorted, verified data
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

# The Data Separation Layer - VascularProfile is our firewall
from vascular_parser import build_vascular_profile, VascularProfile
from files import get_artifact_store

logger = logging.getLogger("shadow-ehr")


class NarrativeRequest(BaseModel):
    include_vision: bool = False
    narrative_type: str = "vascular_intro"  # vascular_intro, discharge_summary, etc.


class NarrativeResponse(BaseModel):
    narrative: str
    sources_used: List[str]
    data_quality_score: float  # How complete was the underlying data?
    generated_at: str


class NarrativeEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.model_id = "gemini-2.0-flash"
        else:
            self.client = None
            logger.warning("NarrativeEngine: No API Key found. AI features disabled.")

    async def generate_narrative(
        self,
        patient_id: str,
        raw_cache_data: Dict[str, Any],
        include_vision: bool = False
    ) -> NarrativeResponse:
        """
        Orchestrates the data sorting and narrative generation.

        1. ABSORB: Take raw cache.
        2. SORT: Run strict extractors (VascularProfile).
        3. SYNTHESIZE: Send *only* sorted data to LLM.
        """
        logger.info("=" * 60)
        logger.info(f"[NARRATIVE] Processing for patient: {patient_id}")

        if not self.client:
            logger.error("[NARRATIVE] No Gemini client available!")
            return NarrativeResponse(
                narrative="AI Service Unavailable. Please configure GEMINI_API_KEY.",
                sources_used=[],
                data_quality_score=0.0,
                generated_at=datetime.now().isoformat()
            )

        # --- STEP 1: THE DATA SEPARATION LAYER ---
        # We do NOT send raw_cache_data to the LLM. We build a typed Profile first.
        logger.info("[NARRATIVE] Step 1: Sorting data through VascularProfile...")

        # Transform raw cache into the format vascular_parser expects
        parser_input = self._transform_cache_to_parser_input(raw_cache_data)

        # Build the typed profile - this is our firewall
        profile: VascularProfile = build_vascular_profile(patient_id, parser_input)

        logger.info(f"[NARRATIVE] Profile built: {len(profile.diagnoses)} diagnoses, "
                   f"{len(profile.antithrombotics)} antithrombotics, "
                   f"{len(profile.vascular_history)} procedures")

        # --- STEP 2: VISION EXTRACTION (Optional) ---
        vision_insights = ""
        doc_sources: List[str] = []
        if include_vision:
            logger.info("[NARRATIVE] Step 2: Processing visual artifacts...")
            vision_insights, doc_sources = await self._extract_from_documents(patient_id)
        else:
            logger.info("[NARRATIVE] Step 2: Skipping vision (not requested)")

        # --- STEP 3: CONTEXT PREPARATION ---
        # Serialize the SORTED profile, not raw JSON
        llm_context = self._prepare_llm_context(profile, vision_insights, raw_cache_data)

        # Calculate data quality score
        quality_score = self._calculate_data_quality(profile, raw_cache_data)
        logger.info(f"[NARRATIVE] Data quality score: {quality_score:.2f}")

        # --- STEP 4: GENERATION ---
        logger.info("[NARRATIVE] Step 3: Generating narrative with Gemini...")

        prompt = f"""
ROLE: Expert Vascular Surgeon's Scribe.
TASK: Write the "History of Present Illness" (HPI) opening paragraph.

INPUT DATA (Sorted & Verified):
{llm_context}

INSTRUCTIONS:
1. Start EXACTLY with: "This is a [AGE] year-old [GENDER]..."
2. List ONLY relevant comorbidities (HTN, HLD, DM, CAD, CKD, COPD, Smoking). Use concise abbreviations.
3. Summarize Surgical History chronologically. If dates are known, use them. If not, say "history of...".
4. Mention critical vascular medications (Antiplatelets/Anticoagulants) only if active.
5. Incorporate insights extracted from documents if they add specific dates or procedures not in the structured data.
6. Style: Professional, medical, concise. No bullet points. Max 4 sentences.
7. If age or gender is unknown, omit those details gracefully.

OUTPUT:
"""

        try:
            # Run the synchronous Gemini call in a thread pool
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1)
                )),
                timeout=30.0
            )
            narrative = response.text.strip()
            logger.info(f"[NARRATIVE] Generated {len(narrative)} chars")

        except asyncio.TimeoutError:
            logger.error("[NARRATIVE] Gemini call timed out after 30 seconds")
            narrative = "Narrative generation timed out. Please try again."
        except Exception as e:
            logger.error(f"[NARRATIVE] Gemini error: {e}")
            logger.exception("Full traceback:")
            narrative = f"Could not generate narrative: {str(e)}"

        sources = ["Structured EHR Data"] + doc_sources

        logger.info("=" * 60)
        return NarrativeResponse(
            narrative=narrative,
            sources_used=sources,
            data_quality_score=quality_score,
            generated_at=datetime.now().isoformat()
        )

    def _transform_cache_to_parser_input(self, raw_cache: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform the main.py cache format to what vascular_parser expects.

        Input (main.py cache):
            {'patient': {...}, 'medications': [...], 'problems': [...], ...}

        Output (vascular_parser format):
            {'demographics': {'data': {...}}, 'medications': {'data': [...]}, ...}
        """
        return {
            "demographics": {"data": raw_cache.get("patient") or {}},
            "medications": {"data": raw_cache.get("medications") or []},
            "problems": {"data": raw_cache.get("problems") or []},
            "labs": {"data": raw_cache.get("labs") or []},
            "notes": {"data": raw_cache.get("notes") or raw_cache.get("note") or []},
            "procedures": {"data": raw_cache.get("surgical_history") or raw_cache.get("procedures") or []},
            "allergies": {"data": raw_cache.get("allergies") or raw_cache.get("allergy") or []},
            "documents": {"data": raw_cache.get("documents") or []},
        }

    def _prepare_llm_context(
        self,
        profile: VascularProfile,
        vision_text: str,
        raw_cache: Dict[str, Any]
    ) -> str:
        """
        Converts the typed VascularProfile into a clean text block.
        This is the ONLY thing the LLM sees - no raw JSON.
        """
        # Extract demographics from raw cache for age/gender
        patient_data = raw_cache.get("patient") or {}

        # Calculate age
        dob = patient_data.get("birthDate") or patient_data.get("dob")
        age = "Unknown age"
        if dob:
            try:
                bday = datetime.strptime(str(dob), "%Y-%m-%d")
                age = f"{(datetime.now() - bday).days // 365} years old"
            except Exception:
                pass

        gender = patient_data.get("gender", "unknown")

        # Format diagnoses - filter for active, focus on relevant comorbidities
        vascular_comorbidities = ["hypertension", "htn", "diabetes", "dm", "hyperlipidemia",
                                   "hld", "cad", "coronary", "ckd", "chronic kidney",
                                   "copd", "smoking", "tobacco", "afib", "atrial fibrillation",
                                   "pvd", "pad", "peripheral"]

        relevant_dx = []
        other_dx = []
        for dx in profile.diagnoses:
            if dx.status == "active":
                dx_lower = dx.name.lower()
                if any(term in dx_lower for term in vascular_comorbidities):
                    relevant_dx.append(dx.name)
                else:
                    other_dx.append(dx.name)

        # Format antithrombotics
        meds = [f"{m.name} ({m.category})" for m in profile.antithrombotics]

        # Format surgical history
        hx = []
        for h in profile.vascular_history:
            if h.date:
                hx.append(f"{h.procedure} ({h.date})")
            else:
                hx.append(h.procedure)

        # Format allergies
        allergies = [f"{a.allergen}: {a.surgical_implication or 'caution'}"
                     for a in profile.critical_allergies]

        context = f"""
PATIENT: {profile.name}
MRN: {profile.mrn}
DEMOGRAPHICS: {age}, {gender}

VERIFIED VASCULAR COMORBIDITIES:
{", ".join(relevant_dx[:10]) if relevant_dx else "None specifically documented"}

OTHER ACTIVE DIAGNOSES:
{", ".join(other_dx[:10]) if other_dx else "None"}

ACTIVE ANTITHROMBOTICS:
{", ".join(meds) if meds else "None documented"}

SURGICAL/VASCULAR HISTORY:
{"; ".join(hx) if hx else "None documented in structured data"}

CRITICAL ALLERGIES:
{", ".join(allergies) if allergies else "None documented"}

DOCUMENT EXTRACTIONS (Vision):
{vision_text if vision_text else "No additional documents processed."}
"""
        return context

    async def _extract_from_documents(self, patient_id: str) -> tuple[str, List[str]]:
        """
        Uses Vision model to read documents/images in the artifact store.
        """
        if not self.client:
            return "", []

        store = get_artifact_store()
        artifacts = store.list_by_patient(patient_id)

        # Sort by date, take top 3 most recent
        recent_artifacts = sorted(
            artifacts,
            key=lambda x: x.stored_at or "",
            reverse=True
        )[:3]

        extracted_info = []
        sources = []

        for art in recent_artifacts:
            # Only process images/PDFs, skip JSON
            if not art.mime_type or "json" in art.mime_type:
                continue

            data = store.get(art.artifact_id)
            if not data:
                continue

            try:
                loop = asyncio.get_event_loop()
                prompt = ("Read this medical document. List any surgical procedures and their dates "
                         "found in the text. Format: Procedure - Date. Be concise.")

                response = await loop.run_in_executor(None, lambda d=data, m=art.mime_type:
                    self.client.models.generate_content(
                        model=self.model_id,
                        contents=[
                            types.Part.from_bytes(data=d, mime_type=m),
                            prompt
                        ]
                    )
                )
                if response.text:
                    extracted_info.append(f"[From {art.original_filename}]: {response.text.strip()}")
                    sources.append(f"Doc: {art.original_filename}")

            except Exception as e:
                logger.error(f"[NARRATIVE] Vision failed on {art.artifact_id}: {e}")

        return "\n".join(extracted_info), sources

    def _calculate_data_quality(self, profile: VascularProfile, raw_cache: Dict[str, Any]) -> float:
        """
        Calculate a data completeness score (0-1).
        Higher score = more confident in the narrative.
        """
        score = 0.0

        # Patient demographics
        if profile.name and profile.name != "Unknown":
            score += 0.15
        if raw_cache.get("patient", {}).get("birthDate"):
            score += 0.10
        if raw_cache.get("patient", {}).get("gender"):
            score += 0.05

        # Clinical data
        if profile.diagnoses:
            score += 0.25
        if profile.antithrombotics:
            score += 0.10
        if profile.vascular_history:
            score += 0.15
        if profile.renal_function:
            score += 0.05
        if profile.coagulation:
            score += 0.05
        if profile.cardiac_clearance:
            score += 0.05
        if profile.critical_allergies:
            score += 0.05

        return min(score, 1.0)


# Global Singleton
_narrative_engine = NarrativeEngine()


def get_narrative_engine():
    return _narrative_engine
