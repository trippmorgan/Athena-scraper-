"""
AI Clinical Summarizer: Intelligent Clinical Context Generation

==============================================================================
PURPOSE
==============================================================================

This module provides AI-powered clinical summarization for vascular surgery
decision support. It transforms raw clinical data into:

1. SURGICAL BRIEFINGS - Pre-op summaries for the surgical team
2. RISK ASSESSMENTS - Automated cardiovascular risk stratification
3. MEDICATION ALERTS - Antithrombotic management recommendations
4. CLINICAL CONTEXTS - Structured prompts for LLM integration

Designed for integration with:
- Claude (Anthropic) - Primary recommendation
- GPT-4 (OpenAI)
- Gemini (Google)
- Local models via Ollama

==============================================================================
CLINICAL RELEVANCE
==============================================================================

For vascular surgery, the key decision points are:

1. ANTITHROMBOTIC MANAGEMENT
   - When to hold clopidogrel/aspirin before surgery
   - Bridging anticoagulation protocols
   - Post-op restart timing

2. CARDIOVASCULAR RISK
   - Lee's Revised Cardiac Risk Index components
   - Diabetes, CKD, CAD presence
   - Functional capacity assessment

3. VASCULAR DISEASE BURDEN
   - Extent of peripheral arterial disease
   - Prior interventions
   - Limb threat classification

==============================================================================
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger("shadow-ehr")


class SummaryType(Enum):
    """Types of clinical summaries available."""
    SURGICAL_BRIEFING = "surgical_briefing"
    RISK_ASSESSMENT = "risk_assessment"
    MEDICATION_ALERT = "medication_alert"
    PREOP_CHECKLIST = "preop_checklist"
    CLINICAL_CONTEXT = "clinical_context"


@dataclass
class ClinicalContext:
    """
    Structured clinical context for LLM prompting.

    This provides all the information an AI needs to generate
    meaningful clinical summaries.
    """
    patient_id: str
    generated_at: str

    # Medications
    total_medications: int
    antithrombotics: List[Dict]
    anticoagulants: List[Dict]
    antiplatelets: List[Dict]
    other_medications: List[Dict]

    # Problems/Diagnoses
    total_problems: int
    vascular_diagnoses: List[Dict]
    cardiovascular_risks: List[Dict]
    other_problems: List[Dict]

    # Risk Factors
    has_diabetes: bool
    has_ckd: bool
    has_cad: bool
    has_chf: bool
    has_stroke_history: bool

    # Vascular Specifics
    pad_present: bool
    claudication: bool
    critical_limb_ischemia: bool
    prior_vascular_intervention: bool

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_prompt(self) -> str:
        """Generate a structured prompt for LLM summarization."""
        return f"""## Clinical Context for Patient {self.patient_id}
Generated: {self.generated_at}

### MEDICATIONS ({self.total_medications} total)

**Antithrombotic Medications ({len(self.antithrombotics)}):**
{self._format_meds(self.antithrombotics)}

**Other Active Medications ({len(self.other_medications)}):**
{self._format_meds(self.other_medications[:10])}  {f"... and {len(self.other_medications)-10} more" if len(self.other_medications) > 10 else ""}

### DIAGNOSES ({self.total_problems} total)

**Vascular Conditions ({len(self.vascular_diagnoses)}):**
{self._format_problems(self.vascular_diagnoses)}

**Cardiovascular Risk Factors ({len(self.cardiovascular_risks)}):**
{self._format_problems(self.cardiovascular_risks)}

### RISK PROFILE
- Diabetes: {"Yes" if self.has_diabetes else "No"}
- Chronic Kidney Disease: {"Yes" if self.has_ckd else "No"}
- Coronary Artery Disease: {"Yes" if self.has_cad else "No"}
- Heart Failure: {"Yes" if self.has_chf else "No"}
- Prior Stroke/TIA: {"Yes" if self.has_stroke_history else "No"}

### VASCULAR STATUS
- Peripheral Arterial Disease: {"Yes" if self.pad_present else "No"}
- Claudication: {"Yes" if self.claudication else "No"}
- Critical Limb Ischemia: {"Yes" if self.critical_limb_ischemia else "No"}
- Prior Vascular Intervention: {"Yes" if self.prior_vascular_intervention else "No"}
"""

    def _format_meds(self, meds: List[Dict]) -> str:
        if not meds:
            return "  None documented"
        lines = []
        for m in meds:
            name = m.get('name', 'Unknown')
            status = m.get('status', 'active')
            lines.append(f"  - {name} ({status})")
        return "\n".join(lines)

    def _format_problems(self, problems: List[Dict]) -> str:
        if not problems:
            return "  None documented"
        lines = []
        for p in problems:
            name = p.get('display_name', 'Unknown')
            icd = p.get('icd10_code', '')
            code_str = f" [{icd}]" if icd else ""
            lines.append(f"  - {name}{code_str}")
        return "\n".join(lines)


class ClinicalSummarizer:
    """
    AI-powered clinical summarization engine.

    Generates clinical summaries using either:
    1. Built-in rule-based templates (fast, no API needed)
    2. External LLM APIs (Claude, GPT-4, Gemini)
    """

    # ICD-10 prefixes for risk factor detection
    DIABETES_CODES = ['E08', 'E09', 'E10', 'E11', 'E13']
    CKD_CODES = ['N18']
    CAD_CODES = ['I25', 'I21', 'I22', 'I23', 'I24']
    CHF_CODES = ['I50']
    STROKE_CODES = ['I63', 'I64', 'G45', 'I61', 'I60']
    PAD_CODES = ['I70', 'I73', 'I74']
    CLI_CODES = ['I70.24', 'I70.25', 'I70.34', 'I70.35', 'I70.44', 'I70.45']

    def __init__(self, api_key: Optional[str] = None, model: str = "claude"):
        """
        Initialize the summarizer.

        Args:
            api_key: Optional API key for LLM service
            model: Model to use ("claude", "gpt4", "gemini", "local", "template")
        """
        self.model = model

        # Load the appropriate API key based on the model
        if api_key:
            self.api_key = api_key
        elif model == "claude":
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        elif model == "gpt4":
            self.api_key = os.environ.get("OPENAI_API_KEY")
        elif model == "gemini":
            self.api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        else:
            self.api_key = None  # template/local don't need keys

        # Log available providers
        available = []
        if os.environ.get("ANTHROPIC_API_KEY"): available.append("claude")
        if os.environ.get("OPENAI_API_KEY"): available.append("gpt4")
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"): available.append("gemini")

        logger.info(f"[AI] Clinical Summarizer initialized (model={model})")
        logger.info(f"[AI] Available LLM providers: {available or ['template only']}")

    def build_clinical_context(
        self,
        patient_id: str,
        medications: List[Dict],
        problems: List[Dict]
    ) -> ClinicalContext:
        """
        Build a structured clinical context from raw data.

        Args:
            patient_id: Patient identifier
            medications: List of extracted medications
            problems: List of extracted problems

        Returns:
            ClinicalContext ready for summarization
        """
        # Categorize medications
        antithrombotics = [m for m in medications if m.get('is_antithrombotic', False)]
        anticoagulants = [m for m in antithrombotics if self._is_anticoagulant(m)]
        antiplatelets = [m for m in antithrombotics if not self._is_anticoagulant(m)]
        other_meds = [m for m in medications if not m.get('is_antithrombotic', False)]

        # Categorize problems
        vascular_dx = [p for p in problems if p.get('is_vascular', False)]
        cv_risks = [p for p in problems if p.get('is_cardiovascular_risk', False)]
        other_probs = [p for p in problems
                       if not p.get('is_vascular', False) and not p.get('is_cardiovascular_risk', False)]

        # Detect specific risk factors from ICD-10 codes
        all_codes = [p.get('icd10_code', '').upper().replace('.', '') for p in problems]

        return ClinicalContext(
            patient_id=patient_id,
            generated_at=datetime.utcnow().isoformat(),
            total_medications=len(medications),
            antithrombotics=antithrombotics,
            anticoagulants=anticoagulants,
            antiplatelets=antiplatelets,
            other_medications=other_meds,
            total_problems=len(problems),
            vascular_diagnoses=vascular_dx,
            cardiovascular_risks=cv_risks,
            other_problems=other_probs,
            has_diabetes=self._has_code_prefix(all_codes, self.DIABETES_CODES),
            has_ckd=self._has_code_prefix(all_codes, self.CKD_CODES),
            has_cad=self._has_code_prefix(all_codes, self.CAD_CODES),
            has_chf=self._has_code_prefix(all_codes, self.CHF_CODES),
            has_stroke_history=self._has_code_prefix(all_codes, self.STROKE_CODES),
            pad_present=self._has_code_prefix(all_codes, self.PAD_CODES),
            claudication=any('claudication' in p.get('display_name', '').lower() for p in problems),
            critical_limb_ischemia=self._has_code_prefix(all_codes, self.CLI_CODES),
            prior_vascular_intervention=any(
                kw in p.get('display_name', '').lower()
                for p in problems
                for kw in ['stent', 'bypass', 'angioplasty', 'endarterectomy', 'amputation']
            )
        )

    def _has_code_prefix(self, codes: List[str], prefixes: List[str]) -> bool:
        """Check if any code starts with any of the given prefixes."""
        for code in codes:
            for prefix in prefixes:
                if code.startswith(prefix.replace('.', '')):
                    return True
        return False

    def _is_anticoagulant(self, med: Dict) -> bool:
        """Check if medication is an anticoagulant (vs antiplatelet)."""
        name = med.get('name', '').lower()
        anticoagulants = [
            'warfarin', 'coumadin', 'heparin', 'enoxaparin', 'lovenox',
            'rivaroxaban', 'xarelto', 'apixaban', 'eliquis', 'dabigatran',
            'pradaxa', 'edoxaban', 'fondaparinux'
        ]
        return any(ac in name for ac in anticoagulants)

    def generate_surgical_briefing(self, context: ClinicalContext) -> str:
        """
        Generate a surgical briefing summary.

        Uses template-based generation for speed and reliability.
        """
        briefing = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    VASCULAR SURGERY BRIEFING                      ║
║                    Patient: {context.patient_id:<20}                ║
║                    Generated: {context.generated_at[:10]}                      ║
╚══════════════════════════════════════════════════════════════════╝

🩸 ANTITHROMBOTIC STATUS
────────────────────────────────────────────────────────────────────
"""
        if context.antithrombotics:
            if context.anticoagulants:
                briefing += "⚠️  ANTICOAGULANTS:\n"
                for med in context.anticoagulants:
                    briefing += f"    • {med['name']}\n"
            if context.antiplatelets:
                briefing += "⚠️  ANTIPLATELETS:\n"
                for med in context.antiplatelets:
                    briefing += f"    • {med['name']}\n"
            briefing += "\n    ⏰ CONSIDER: Timing of hold/restart per institutional protocol\n"
        else:
            briefing += "    ✓ No antithrombotics documented\n"

        briefing += """
🏥 VASCULAR DIAGNOSES
────────────────────────────────────────────────────────────────────
"""
        if context.vascular_diagnoses:
            for dx in context.vascular_diagnoses:
                code = f" [{dx.get('icd10_code', '')}]" if dx.get('icd10_code') else ""
                briefing += f"    • {dx['display_name']}{code}\n"
        else:
            briefing += "    None documented\n"

        # Risk score
        risk_count = sum([
            context.has_diabetes,
            context.has_ckd,
            context.has_cad,
            context.has_chf,
            context.has_stroke_history
        ])

        briefing += f"""
❤️ CARDIOVASCULAR RISK (RCRI-like)
────────────────────────────────────────────────────────────────────
    Risk Factors Present: {risk_count}/5
    • Diabetes:     {"✓ YES" if context.has_diabetes else "✗ No"}
    • CKD:          {"✓ YES" if context.has_ckd else "✗ No"}
    • CAD/Ischemia: {"✓ YES" if context.has_cad else "✗ No"}
    • Heart Failure:{"✓ YES" if context.has_chf else "✗ No"}
    • Prior Stroke: {"✓ YES" if context.has_stroke_history else "✗ No"}

    Estimated Cardiac Risk: {"HIGH" if risk_count >= 3 else "MODERATE" if risk_count >= 1 else "LOW"}
"""

        if context.critical_limb_ischemia:
            briefing += """
🚨 CRITICAL LIMB ISCHEMIA
────────────────────────────────────────────────────────────────────
    ⚠️  CLI DOCUMENTED - Urgent revascularization may be indicated
"""

        briefing += """
════════════════════════════════════════════════════════════════════
"""
        return briefing

    def generate_medication_alert(self, context: ClinicalContext) -> str:
        """Generate medication management alert for surgical planning."""
        if not context.antithrombotics:
            return "✓ No antithrombotic medications requiring management"

        alert = "⚠️ ANTITHROMBOTIC MANAGEMENT REQUIRED\n\n"

        if context.anticoagulants:
            alert += "ANTICOAGULANTS (typically hold 2-5 days pre-op):\n"
            for med in context.anticoagulants:
                alert += f"  • {med['name']}\n"
            alert += "\n"

        if context.antiplatelets:
            alert += "ANTIPLATELETS (per surgical indication):\n"
            for med in context.antiplatelets:
                name = med['name'].lower()
                if 'clopidogrel' in name or 'plavix' in name:
                    alert += f"  • {med['name']} - Consider 5-7 day hold for major surgery\n"
                elif 'aspirin' in name:
                    alert += f"  • {med['name']} - Often continued for vascular procedures\n"
                else:
                    alert += f"  • {med['name']}\n"

        return alert

    async def generate_llm_summary(
        self,
        context: ClinicalContext,
        summary_type: SummaryType = SummaryType.SURGICAL_BRIEFING
    ) -> str:
        """
        Generate summary using external LLM API.

        Args:
            context: Clinical context to summarize
            summary_type: Type of summary to generate

        Returns:
            LLM-generated summary string
        """
        if not self.api_key:
            logger.warning("[AI] No API key configured, falling back to template")
            return self.generate_surgical_briefing(context)

        prompt = self._build_llm_prompt(context, summary_type)

        if self.model == "claude":
            return await self._call_claude(prompt)
        elif self.model == "gpt4":
            return await self._call_openai(prompt)
        elif self.model == "gemini":
            return await self._call_gemini(prompt)
        else:
            # Template fallback
            return self.generate_surgical_briefing(context)

    def _build_llm_prompt(self, context: ClinicalContext, summary_type: SummaryType) -> str:
        """Build the prompt for LLM summarization."""
        system_prompt = """You are a clinical decision support assistant for vascular surgery.
Your role is to provide concise, actionable clinical summaries for surgical teams.
Focus on information relevant to perioperative management:
- Antithrombotic medications and management
- Cardiovascular risk factors
- Vascular disease extent
- Key comorbidities affecting surgical planning

Be concise, use bullet points, and highlight critical safety information."""

        clinical_data = context.to_prompt()

        if summary_type == SummaryType.SURGICAL_BRIEFING:
            task = "Generate a surgical briefing for this patient. Focus on key information the surgical team needs."
        elif summary_type == SummaryType.RISK_ASSESSMENT:
            task = "Generate a cardiovascular risk assessment for this patient undergoing vascular surgery."
        elif summary_type == SummaryType.MEDICATION_ALERT:
            task = "Generate medication alerts for this patient, focusing on perioperative management of antithrombotics."
        else:
            task = "Generate a clinical summary for this patient."

        return f"{system_prompt}\n\n{clinical_data}\n\nTask: {task}"

    async def _call_claude(self, prompt: str) -> str:
        """Call Claude API."""
        try:
            import anthropic
            api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                return "ANTHROPIC_API_KEY not set in .env"
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except ImportError:
            logger.error("[AI] anthropic package not installed. Run: pip install anthropic")
            return "anthropic package not installed. Run: pip install anthropic"
        except Exception as e:
            logger.error(f"[AI] Claude API error: {e}")
            return f"Error calling Claude API: {e}"

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
            api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return "OPENAI_API_KEY not set in .env"
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024
            )
            return response.choices[0].message.content
        except ImportError:
            logger.error("[AI] openai package not installed. Run: pip install openai")
            return "openai package not installed. Run: pip install openai"
        except Exception as e:
            logger.error(f"[AI] OpenAI API error: {e}")
            return f"Error calling OpenAI API: {e}"

    async def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini API."""
        try:
            import google.generativeai as genai
            api_key = self.api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return "GOOGLE_API_KEY not set in .env"
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return response.text
        except ImportError:
            logger.error("[AI] google-generativeai package not installed")
            return "Google AI package not installed"
        except Exception as e:
            logger.error(f"[AI] Gemini API error: {e}")
            return f"Error calling Gemini API: {e}"


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

_summarizer: Optional[ClinicalSummarizer] = None


def get_summarizer(model: str = "template") -> ClinicalSummarizer:
    """Get or create the global summarizer instance."""
    global _summarizer
    if _summarizer is None or _summarizer.model != model:
        _summarizer = ClinicalSummarizer(model=model)
    return _summarizer


def generate_context(
    patient_id: str,
    medications: List[Dict],
    problems: List[Dict]
) -> ClinicalContext:
    """
    Generate clinical context from patient data.

    This is the main entry point for context generation.
    """
    summarizer = get_summarizer()
    return summarizer.build_clinical_context(patient_id, medications, problems)


def generate_briefing(context: ClinicalContext) -> str:
    """Generate a surgical briefing from clinical context."""
    summarizer = get_summarizer()
    return summarizer.generate_surgical_briefing(context)


def generate_med_alert(context: ClinicalContext) -> str:
    """Generate medication management alert."""
    summarizer = get_summarizer()
    return summarizer.generate_medication_alert(context)
