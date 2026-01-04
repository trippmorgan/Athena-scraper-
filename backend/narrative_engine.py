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
TASK: Write a comprehensive clinical summary for a vascular surgery patient.

INPUT DATA (Sorted & Verified):
{llm_context}

INSTRUCTIONS:
1. Start with: "This is a [AGE] year-old [GENDER] (DOB: [DOB]) with a history of..."
   - Example: "This is a 64 year-old female (DOB: 10/10/1960) with a history of..."
2. Include ALL vascular diagnoses with their ICD-10 codes in parentheses, e.g., "peripheral arterial disease (ICD-10: I70.213)"
3. List relevant comorbidities using standard abbreviations (HTN, HLD, DM, CAD, CKD, COPD, AFib, tobacco use)
4. Include presenting complaints: rest pain, claudication, ulcers, etc. with ICD-10 codes when available
5. Mention active antithrombotic medications (Antiplatelets/Anticoagulants)
6. Include surgical/vascular history if documented
7. Style: Professional, thorough, suitable for surgical documentation
8. ALWAYS include patient demographics (age, sex, DOB) at the start if available

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
        # Try to recover patient data from 'unknown' if not in 'patient' field
        patient_data = raw_cache.get("patient") or {}
        if not patient_data:
            # Search unknown items for patient demographics
            unknown_items = raw_cache.get("unknown") or []
            for item in unknown_items:
                if isinstance(item, dict):
                    data = item.get("data", {})
                    if isinstance(data, dict) and "patient" in data:
                        patient_data = data["patient"]
                        logger.info(f"[NARRATIVE] Recovered patient data from unknown: {patient_data.get('LastName', 'Unknown')}")
                        break

        # Transform Athena format to FHIR-like format if needed
        if patient_data and "LastName" in patient_data:
            # Convert Athena format to standard format
            dob_obj = patient_data.get("BirthDate", {})
            dob = dob_obj.get("Date") if isinstance(dob_obj, dict) else dob_obj
            patient_data = {
                "name": patient_data.get("LastName", "Unknown"),
                "birthDate": dob,
                "gender": patient_data.get("Sex", "unknown").lower(),
            }

        # Get problems from cache
        problems_data = raw_cache.get("problems") or []

        # RECOVER DIAGNOSES: If problems empty, extract from historical_clinical_encounters in unknown
        if not problems_data:
            unknown_items = raw_cache.get("unknown") or []
            recovered_diagnoses = []
            seen_names = set()

            for item in unknown_items:
                if isinstance(item, dict):
                    data = item.get("data", {})
                    if isinstance(data, dict):
                        # Check both historical and initial encounters
                        encounters = (data.get("historical_clinical_encounters", []) +
                                     data.get("initial_historical_clinical_encounters", []))
                        for enc in encounters:
                            diagnoses = enc.get("Diagnoses", [])
                            for dx in diagnoses:
                                name = dx.get("Name", "")
                                if name and name not in seen_names:
                                    seen_names.add(name)
                                    # Extract ICD-10 code
                                    icd_codes = dx.get("SnomedICDCodes", [])
                                    icd10 = next((c.get("Code") for c in icd_codes
                                                 if c.get("CodeSet") == "ICD10"), None)
                                    snomed = dx.get("Code", {}).get("Code") if isinstance(dx.get("Code"), dict) else None

                                    recovered_diagnoses.append({
                                        "display_name": name,
                                        "icd10_code": icd10,
                                        "snomed_code": snomed,
                                        "clinical_status": "active"
                                    })

            if recovered_diagnoses:
                logger.info(f"[NARRATIVE] RECOVERED {len(recovered_diagnoses)} diagnoses from historical encounters")
                problems_data = recovered_diagnoses

        return {
            "demographics": {"data": patient_data},
            "medications": {"data": raw_cache.get("medications") or []},
            "problems": {"data": problems_data},
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
        # Extract demographics - check both 'patient' field and 'unknown' array
        patient_data = raw_cache.get("patient") or {}
        logger.info(f"[NARRATIVE] Patient data keys: {list(patient_data.keys()) if patient_data else 'EMPTY'}")

        # If patient is empty, search in unknown array (same as _transform_cache_to_parser_input)
        if not patient_data:
            unknown_items = raw_cache.get("unknown") or []
            for item in unknown_items:
                if isinstance(item, dict):
                    data = item.get("data", {})
                    if isinstance(data, dict):
                        # Check for available_contacts_and_consents (Athena UPPERCASE format)
                        contacts = data.get("available_contacts_and_consents")
                        if isinstance(contacts, dict) and (contacts.get("FIRSTNAME") or contacts.get("LASTNAME")):
                            # Convert to expected format
                            patient_data = {
                                "FirstName": contacts.get("FIRSTNAME", ""),
                                "LastName": contacts.get("LASTNAME", ""),
                                "PatientId": contacts.get("PATIENTID", ""),
                                # Note: available_contacts_and_consents does NOT have DOB/Gender
                            }
                            logger.info(f"[NARRATIVE] Found patient in available_contacts_and_consents: {patient_data.get('FirstName')} {patient_data.get('LastName')}")
                            break
                        # Check for patient object (legacy path)
                        if "patient" in data:
                            patient_data = data["patient"]
                            break

        # Handle Athena format (LastName, BirthDate, Sex) vs FHIR format (name, birthDate, gender)
        # Also handle UPPERCASE format from available_contacts_and_consents
        if "LastName" in patient_data:
            # Athena format
            dob_obj = patient_data.get("BirthDate", {})
            dob = dob_obj.get("Date") if isinstance(dob_obj, dict) else dob_obj
            gender = (patient_data.get("Sex") or patient_data.get("GenderMarker") or "unknown").lower()
            if gender == "f":
                gender = "female"
            elif gender == "m":
                gender = "male"
            logger.info(f"[NARRATIVE] Athena format - DOB obj: {dob_obj}, DOB: {dob}, Gender: {gender}")
        else:
            # FHIR format - also try common Athena field names
            dob = (patient_data.get("birthDate") or patient_data.get("dob") or
                   patient_data.get("DOB") or patient_data.get("dateOfBirth") or
                   patient_data.get("DateOfBirth"))
            gender = (patient_data.get("gender") or patient_data.get("Gender") or
                     patient_data.get("sex") or patient_data.get("Sex") or "unknown")
            logger.info(f"[NARRATIVE] FHIR format - DOB: {dob}, Gender: {gender}")

        # Calculate age - handle multiple date formats
        age = "Unknown age"
        dob_str = None
        if dob:
            dob_parsed = None
            dob_raw = str(dob).strip()

            # Try multiple date formats
            date_formats = [
                "%Y-%m-%d",       # 1960-10-10 (ISO)
                "%m/%d/%Y",       # 10/10/1960 (US)
                "%m-%d-%Y",       # 10-10-1960
                "%Y/%m/%d",       # 1960/10/10
                "%d/%m/%Y",       # 10/10/1960 (EU)
                "%Y%m%d",         # 19601010 (compact)
            ]

            for fmt in date_formats:
                try:
                    dob_parsed = datetime.strptime(dob_raw, fmt)
                    break
                except ValueError:
                    continue

            if dob_parsed:
                years = (datetime.now() - dob_parsed).days // 365
                age = f"{years} years old"
                dob_str = dob_parsed.strftime("%m/%d/%Y")
            else:
                # Couldn't parse, use raw string
                dob_str = dob_raw
                logger.warning(f"[NARRATIVE] Could not parse DOB: {dob_raw}")

        # Format diagnoses WITH ICD-10 codes - separate into categories
        vascular_keywords = ["atherosclerosis", "arterial", "venous", "vascular", "aneurysm",
                             "stenosis", "occlusion", "claudication", "ischemic", "ulcer",
                             "pvd", "pad", "carotid", "aortic", "bypass", "stent"]
        comorbidity_keywords = ["hypertension", "htn", "diabetes", "dm", "hyperlipidemia",
                                "hld", "cad", "coronary", "ckd", "chronic kidney",
                                "copd", "smoking", "tobacco", "afib", "atrial fibrillation",
                                "heart", "cardiac"]

        def format_dx_with_icd(dx):
            """Format diagnosis with ICD-10 code if available."""
            if dx.icd10_code:
                return f"{dx.name} (ICD-10: {dx.icd10_code})"
            return dx.name

        vascular_dx = []
        comorbidity_dx = []
        other_dx = []
        for dx in profile.diagnoses:
            if dx.status == "active":
                dx_lower = dx.name.lower()
                formatted = format_dx_with_icd(dx)
                if any(term in dx_lower for term in vascular_keywords):
                    vascular_dx.append(formatted)
                elif any(term in dx_lower for term in comorbidity_keywords):
                    comorbidity_dx.append(formatted)
                else:
                    other_dx.append(formatted)

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
DOB: {dob_str if dob_str else "Unknown"}
AGE: {age}
SEX: {gender.upper() if gender != "unknown" else "Unknown"}

VASCULAR DIAGNOSES:
{chr(10).join(f"- {d}" for d in vascular_dx) if vascular_dx else "None documented"}

CARDIOVASCULAR RISK FACTORS/COMORBIDITIES:
{chr(10).join(f"- {d}" for d in comorbidity_dx) if comorbidity_dx else "None documented"}

OTHER ACTIVE DIAGNOSES:
{chr(10).join(f"- {d}" for d in other_dx) if other_dx else "None"}

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
            logger.info("[NARRATIVE] No Gemini client, skipping vision extraction")
            return "", []

        try:
            store = get_artifact_store()
            if store is None:
                logger.warning("[NARRATIVE] Artifact store is None")
                return "", []

            artifacts = store.list_by_patient(patient_id)
            if artifacts is None:
                logger.warning("[NARRATIVE] list_by_patient returned None")
                return "", []

            logger.info(f"[NARRATIVE] Found {len(artifacts)} artifacts for patient {patient_id}")

            # Sort by date, take top 3 most recent
            recent_artifacts = sorted(
                [a for a in artifacts if a is not None],
                key=lambda x: x.stored_at or "",
                reverse=True
            )[:3]
        except Exception as e:
            logger.error(f"[NARRATIVE] Error accessing artifact store: {e}")
            return "", []

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

        # Patient demographics - handle explicit None values
        patient_data = raw_cache.get("patient") or {}
        if profile.name and profile.name != "Unknown":
            score += 0.15
        if patient_data.get("birthDate"):
            score += 0.10
        if patient_data.get("gender"):
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
