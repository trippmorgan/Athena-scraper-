"""
Narrative Engine: The Cognitive Layer
Generates clinical narratives from structured data + unstructured artifacts (Vision).
"""

import os
import logging
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel

# Vision/LLM Provider
from google import genai
from google.genai import types

from files import get_artifact_store, StoredArtifact

# Use the main logger so logs appear together
logger = logging.getLogger("shadow-ehr")

class NarrativeRequest(BaseModel):
    include_vision: bool = False
    focus_areas: List[str] = ["vascular_history", "comorbidities", "medications"]

class NarrativeResponse(BaseModel):
    narrative: str
    sources_used: List[str]
    confidence: str
    generated_at: str

class NarrativeEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
            self.model_id = "gemini-2.0-flash" # High speed, multimodal
        else:
            self.client = None
            logger.warning("NarrativeEngine: No API Key found. AI features disabled.")

    async def generate_narrative(self, patient_id: str, clinical_data: Dict[str, Any], include_vision: bool = False) -> NarrativeResponse:
        """
        Orchestrates the data gathering and LLM generation.
        """
        logger.info(f"[NARRATIVE] generate_narrative called for {patient_id}")
        logger.info(f"[NARRATIVE] Clinical data keys: {list(clinical_data.keys())}")
        logger.info(f"[NARRATIVE] Medications count: {len(clinical_data.get('medications', []))}")
        logger.info(f"[NARRATIVE] Problems count: {len(clinical_data.get('problems', []))}")

        if not self.client:
            logger.error("[NARRATIVE] No Gemini client available!")
            return NarrativeResponse(
                narrative="AI Service Unavailable. Please configure GEMINI_API_KEY.",
                sources_used=[],
                confidence="none",
                generated_at=datetime.now().isoformat()
            )

        # 1. Build the Structured Context (The "Skeleton")
        logger.info("[NARRATIVE] Building structured context...")
        context_str = self._build_structured_context(clinical_data)
        logger.info(f"[NARRATIVE] Context built: {len(context_str)} chars")
        sources = ["Structured EHR Data"]

        # 2. (Optional) Vision Processing of Artifacts
        vision_context = ""
        if include_vision:
            vision_context, artifact_sources = self._process_visual_artifacts(patient_id)
            if vision_context:
                context_str += f"\n\n=== EXTRACTED FROM SCANNED DOCUMENTS ===\n{vision_context}"
                sources.extend(artifact_sources)

        # 3. Construct the Prompt
        prompt = f"""
        ROLE: Vascular Surgery Scribe
        TASK: Synthesize the provided patient data into a concise introductory narrative.
        
        FORMAT REQUIREMENT:
        "This is a [AGE] year-old [SEX] with a history of [KEY COMORBIDITIES]. Her/His surgical history is significant for [VASCULAR PROCEDURES]."
        
        RULES:
        1. Start exactly with "This is a..."
        2. List comorbidities relevant to vascular risk (HTN, HLD, DM, CAD, Smoking, CKD).
        3. For surgical history, prioritize: Carotid, Aortic, and Peripheral bypass/stents. Include dates if available.
        4. Do not list medications unless they are relevant anticoagulants (e.g. "currently on Warfarin").
        5. Keep it under 4 sentences. 
        6. If dates are missing, omit them rather than guessing.

        INPUT DATA:
        {context_str}
        """
        logger.info(f"[NARRATIVE] Full prompt being sent to Gemini:\n{prompt}")

        # 4. Call LLM (run synchronous call in thread pool with timeout)
        try:
            logger.info(f"Calling Gemini ({self.model_id}) with context: {len(context_str)} chars")
            logger.debug(f"Context preview: {context_str[:500]}...")

            # Run the synchronous Gemini call in a thread pool to not block async
            def call_gemini():
                return self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1, # Deterministic
                    )
                )

            # Run with 30 second timeout
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, call_gemini),
                timeout=30.0
            )

            logger.info(f"[NARRATIVE] Raw Gemini response object: {response}")
            narrative = response.text.strip()
            logger.info(f"Gemini response received: {len(narrative)} chars")
            logger.debug(f"Narrative preview: {narrative[:200]}...")
        except asyncio.TimeoutError:
            logger.error("Gemini call timed out after 30 seconds")
            narrative = "Narrative generation timed out. Please try again."
        except Exception as e:
            logger.error(f"LLM Generation failed: {e}")
            logger.exception("Full Gemini error traceback:")
            narrative = f"Error generating narrative: {str(e)}"

        return NarrativeResponse(
            narrative=narrative,
            sources_used=sources,
            confidence="high" if vision_context else "medium",
            generated_at=datetime.now().isoformat()
        )

    def _build_structured_context(self, data: Dict[str, Any]) -> str:
        """Flattens the cache into a string for the LLM."""
        logger.info("[NARRATIVE] _build_structured_context starting...")
        logger.info(f"[NARRATIVE] Input data keys: {list(data.keys())}")

        # CRITICAL: Use `or {}` to handle None/False values, not just missing keys
        pt = data.get('patient') or {}
        meds = data.get('medications') or []
        probs = data.get('problems') or []
        history = data.get('surgical_history') or []

        logger.info(f"[NARRATIVE] Patient data: {bool(pt)}, keys: {list(pt.keys()) if pt else 'none'}")
        logger.info(f"[NARRATIVE] Medications: {len(meds)} items")
        logger.info(f"[NARRATIVE] Problems: {len(probs)} items")
        logger.info(f"[NARRATIVE] Surgical history: {len(history)} items")

        # Log sample of medications if available
        if meds:
            sample_meds = [m.get('name', str(m)[:50]) if isinstance(m, dict) else str(m)[:50] for m in meds[:5]]
            logger.info(f"[NARRATIVE] Sample medications: {sample_meds}")

        # Log sample of problems if available
        if probs:
            # Problems may have 'display_name', 'display', or 'name' depending on source
            sample_probs = [p.get('display_name', p.get('display', p.get('name', str(p)[:50]))) if isinstance(p, dict) else str(p)[:50] for p in probs[:5]]
            logger.info(f"[NARRATIVE] Sample problems: {sample_probs}")

        # Calculate Age
        dob = pt.get('birthDate') if isinstance(pt, dict) else None
        age = "Unknown"
        if dob:
            try:
                bday = datetime.strptime(dob, "%Y-%m-%d")
                age = (datetime.now() - bday).days // 365
                logger.info(f"[NARRATIVE] Calculated age: {age}")
            except Exception as e:
                logger.warning(f"[NARRATIVE] Could not parse DOB: {dob}, error: {e}")

        # Build summary for LLM - handle varying data structures
        gender = pt.get('gender', 'unknown') if isinstance(pt, dict) else 'unknown'

        # Extract problem names - try multiple possible keys
        problem_names = []
        for p in probs[:15]:
            if isinstance(p, dict):
                name = p.get('display_name') or p.get('display') or p.get('name') or p.get('description') or 'Unknown'
                problem_names.append(name)
            else:
                problem_names.append(str(p))

        # Extract medication names
        med_names = []
        for m in meds[:15]:
            if isinstance(m, dict):
                name = m.get('name') or m.get('medication') or m.get('drug') or 'Unknown'
                med_names.append(name)
            else:
                med_names.append(str(m))

        # Extract surgical history
        surgery_list = []
        for h in history:
            if isinstance(h, dict):
                proc = h.get('procedure', 'Unknown procedure')
                date = h.get('date', '')
                surgery_list.append(f"{proc} ({date})" if date else proc)

        summary = {
            "Demographics": f"{age}-year-old {gender}",
            "Active Problems": problem_names,
            "Medications": med_names,
            "Known Surgical History (Structured)": surgery_list
        }

        logger.info(f"[NARRATIVE] Summary built: {len(problem_names)} problems, {len(med_names)} meds")
        return json.dumps(summary, indent=2)

    def _process_visual_artifacts(self, patient_id: str) -> tuple[str, List[str]]:
        """
        Uses Gemini Vision to read PDFs/Images in the artifact store.
        """
        store = get_artifact_store()
        artifacts = store.list_by_patient(patient_id)
        
        extracted_texts = []
        sources = []

        # Process top 3 most recent artifacts to save latency
        # Ideally, filter for 'Note', 'Report', or 'Scan' types
        target_artifacts = sorted(artifacts, key=lambda x: x.stored_at or "", reverse=True)[:3]

        for art in target_artifacts:
            # We can only process images directly or PDFs if supported by the library/model
            # For this implementation, we assume images (jpg/png) or convert PDFs
            if not art.mime_type or not ('image' in art.mime_type or 'pdf' in art.mime_type):
                continue

            file_bytes = store.get(art.artifact_id)
            if not file_bytes:
                continue

            try:
                prompt = "Extract surgical history and dates from this document. Ignore header/footer boilerplate."
                
                # Direct byte submission to Gemini
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=art.mime_type),
                        prompt
                    ]
                )
                
                if response.text:
                    extracted_texts.append(f"--- Document: {art.original_filename} ---\n{response.text}")
                    sources.append(f"Vision: {art.original_filename}")
                    
            except Exception as e:
                logger.error(f"Vision processing failed for {art.artifact_id}: {e}")

        return "\n".join(extracted_texts), sources

# Global Singleton
_narrative_engine = NarrativeEngine()

def get_narrative_engine():
    return _narrative_engine