"""
Vascular Surgery Extractors: Disease-Specific Clinical Intelligence

This module extracts and interprets vascular-specific clinical data for
preoperative surgical planning. It provides structured assessments for:

1. PAD (Peripheral Arterial Disease)
   - ABI/TBI values and interpretation
   - Claudication symptoms and walking distance
   - Rutherford classification
   - Wound/gangrene staging (WIfI)

2. Carotid Disease
   - Stenosis percentage and methodology
   - Symptomatic vs asymptomatic classification
   - Plaque characteristics
   - Contralateral disease status

3. AAA (Abdominal Aortic Aneurysm)
   - Diameter measurements and growth rate
   - Rupture risk assessment
   - Anatomic suitability (EVAR vs Open)
   - Iliac involvement

4. Antithrombotic Bridging
   - Medication hold recommendations
   - Restart timing
   - Bridging anticoagulation protocols
   - Thromboembolic vs bleeding risk balance

All extractors produce structured data for AI summarization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# ENUMERATIONS & CONSTANTS
# ==============================================================================

class RutherfordClass(Enum):
    """Rutherford Classification for Chronic Limb Ischemia."""
    CLASS_0 = (0, "Asymptomatic")
    CLASS_1 = (1, "Mild claudication")
    CLASS_2 = (2, "Moderate claudication")
    CLASS_3 = (3, "Severe claudication")
    CLASS_4 = (4, "Ischemic rest pain")
    CLASS_5 = (5, "Minor tissue loss")
    CLASS_6 = (6, "Major tissue loss")

    def __init__(self, grade: int, description: str):
        self.grade = grade
        self.description = description


class FontaineStage(Enum):
    """Fontaine Classification for PAD."""
    STAGE_I = (1, "Asymptomatic")
    STAGE_IIA = (2, "Mild claudication (>200m)")
    STAGE_IIB = (3, "Moderate-severe claudication (<200m)")
    STAGE_III = (4, "Ischemic rest pain")
    STAGE_IV = (5, "Ulceration or gangrene")


class WIfIClass(Enum):
    """WIfI (Wound, Ischemia, foot Infection) Classification."""
    VERY_LOW = 1
    LOW = 2
    MODERATE = 3
    HIGH = 4


class CarotidSymptomStatus(Enum):
    """Carotid symptom classification."""
    ASYMPTOMATIC = "asymptomatic"
    SYMPTOMATIC_TIA = "symptomatic_tia"
    SYMPTOMATIC_STROKE = "symptomatic_stroke"
    SYMPTOMATIC_AMAUROSIS = "symptomatic_amaurosis"
    UNKNOWN = "unknown"


class AneurysmRuptureRisk(Enum):
    """AAA rupture risk categories."""
    LOW = "low"           # <4.0cm
    MODERATE = "moderate" # 4.0-5.4cm
    HIGH = "high"         # 5.5-5.9cm
    VERY_HIGH = "very_high"  # >=6.0cm or rapid growth


class EVARSuitability(Enum):
    """EVAR anatomic suitability."""
    SUITABLE = "suitable"
    CHALLENGING = "challenging"
    UNSUITABLE = "unsuitable"
    UNKNOWN = "unknown"


# ==============================================================================
# PAD (PERIPHERAL ARTERIAL DISEASE) EXTRACTOR
# ==============================================================================

@dataclass
class ABIReading:
    """Single ABI measurement."""
    side: str  # "left" or "right"
    value: float
    date: Optional[str] = None
    method: Optional[str] = None  # "doppler", "plethysmography"

    @property
    def interpretation(self) -> str:
        """Clinical interpretation of ABI value."""
        if self.value > 1.4:
            return "Non-compressible (calcified vessels)"
        elif self.value >= 1.0:
            return "Normal"
        elif self.value >= 0.9:
            return "Borderline"
        elif self.value >= 0.7:
            return "Mild PAD"
        elif self.value >= 0.5:
            return "Moderate PAD"
        elif self.value >= 0.3:
            return "Severe PAD"
        else:
            return "Critical limb ischemia"


@dataclass
class TBIReading:
    """Toe-Brachial Index measurement."""
    side: str
    value: float
    date: Optional[str] = None

    @property
    def interpretation(self) -> str:
        if self.value >= 0.7:
            return "Normal"
        elif self.value >= 0.5:
            return "Mild-moderate PAD"
        elif self.value >= 0.3:
            return "Severe PAD"
        else:
            return "Critical limb ischemia"


@dataclass
class PADAssessment:
    """Complete PAD assessment for a patient."""
    patient_id: str
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # ABI/TBI measurements
    abi_readings: List[ABIReading] = field(default_factory=list)
    tbi_readings: List[TBIReading] = field(default_factory=list)

    # Clinical symptoms
    has_claudication: bool = False
    claudication_distance_meters: Optional[int] = None
    rest_pain: bool = False
    tissue_loss: bool = False
    gangrene: bool = False

    # Classification
    rutherford_class: Optional[int] = None
    fontaine_stage: Optional[int] = None
    wifi_wound: Optional[int] = None
    wifi_ischemia: Optional[int] = None
    wifi_infection: Optional[int] = None

    # Anatomic findings
    affected_segments: List[str] = field(default_factory=list)  # e.g., ["SFA", "popliteal", "tibial"]
    occlusions: List[str] = field(default_factory=list)
    stenoses: List[Dict] = field(default_factory=list)  # {"segment": "SFA", "percent": 80}

    # Prior interventions
    prior_bypass: List[str] = field(default_factory=list)  # e.g., ["fem-pop bypass 2020"]
    prior_angioplasty: List[str] = field(default_factory=list)
    prior_stents: List[str] = field(default_factory=list)
    prior_amputation: Optional[str] = None  # e.g., "BKA left 2019"

    def worst_abi(self) -> Optional[ABIReading]:
        """Get the worst (lowest) ABI reading."""
        valid = [a for a in self.abi_readings if 0 < a.value <= 1.4]
        return min(valid, key=lambda x: x.value) if valid else None

    def rutherford_description(self) -> str:
        """Get Rutherford class description."""
        if self.rutherford_class is None:
            return "Not classified"
        for rc in RutherfordClass:
            if rc.grade == self.rutherford_class:
                return f"Rutherford {rc.grade}: {rc.description}"
        return f"Rutherford {self.rutherford_class}"

    def cli_present(self) -> bool:
        """Check if Critical Limb Ischemia is present."""
        if self.rest_pain or self.tissue_loss or self.gangrene:
            return True
        if self.rutherford_class and self.rutherford_class >= 4:
            return True
        worst = self.worst_abi()
        if worst and worst.value < 0.4:
            return True
        return False

    def amputation_risk(self) -> str:
        """Estimate 1-year amputation risk based on WIfI."""
        if all([self.wifi_wound is not None, self.wifi_ischemia is not None, self.wifi_infection is not None]):
            total = self.wifi_wound + self.wifi_ischemia + self.wifi_infection
            if total <= 3:
                return "Very Low (<5%)"
            elif total <= 5:
                return "Low (5-10%)"
            elif total <= 7:
                return "Moderate (10-25%)"
            else:
                return "High (>25%)"
        return "Not calculated"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "patient_id": self.patient_id,
            "assessed_at": self.assessed_at,
            "abi_readings": [{"side": a.side, "value": a.value, "interpretation": a.interpretation} for a in self.abi_readings],
            "tbi_readings": [{"side": t.side, "value": t.value, "interpretation": t.interpretation} for t in self.tbi_readings],
            "worst_abi": self.worst_abi().value if self.worst_abi() else None,
            "has_claudication": self.has_claudication,
            "claudication_distance_meters": self.claudication_distance_meters,
            "rest_pain": self.rest_pain,
            "tissue_loss": self.tissue_loss,
            "gangrene": self.gangrene,
            "rutherford_class": self.rutherford_class,
            "rutherford_description": self.rutherford_description(),
            "cli_present": self.cli_present(),
            "amputation_risk": self.amputation_risk(),
            "affected_segments": self.affected_segments,
            "occlusions": self.occlusions,
            "prior_interventions": {
                "bypass": self.prior_bypass,
                "angioplasty": self.prior_angioplasty,
                "stents": self.prior_stents,
                "amputation": self.prior_amputation,
            }
        }


class PADExtractor:
    """Extracts PAD-specific data from clinical records."""

    # Keywords for symptom detection
    CLAUDICATION_KEYWORDS = [
        'claudication', 'leg pain walking', 'calf pain', 'thigh pain walking',
        'buttock pain walking', 'intermittent claudication', 'walking distance'
    ]

    REST_PAIN_KEYWORDS = [
        'rest pain', 'night pain', 'pain at rest', 'nocturnal pain',
        'ischemic rest pain', 'dependent rubor'
    ]

    TISSUE_LOSS_KEYWORDS = [
        'ulcer', 'wound', 'tissue loss', 'non-healing', 'gangrene',
        'necrosis', 'toe gangrene', 'heel ulcer', 'ischemic ulcer'
    ]

    SEGMENT_PATTERNS = {
        'aortoiliac': r'aort[oa][\-\s]?iliac|iliac|CIA|EIA',
        'CFA': r'common femoral|CFA',
        'SFA': r'superficial femoral|SFA',
        'profunda': r'profunda|deep femoral|PFA',
        'popliteal': r'popliteal|pop',
        'tibial': r'tibial|tibio|AT|PT|peroneal',
        'pedal': r'pedal|dorsalis|plantar|DP|ATA|PTA',
    }

    def extract(self, patient_id: str, clinical_data: Dict[str, Any]) -> PADAssessment:
        """
        Extract PAD assessment from clinical data.

        Args:
            patient_id: Patient identifier
            clinical_data: Dict containing medications, problems, vitals, notes

        Returns:
            PADAssessment with extracted data
        """
        assessment = PADAssessment(patient_id=patient_id)

        # Extract from problems/diagnoses
        problems = clinical_data.get('problems', [])
        self._extract_from_problems(assessment, problems)

        # Extract from vitals (ABI readings)
        vitals = clinical_data.get('vitals', [])
        self._extract_abi_from_vitals(assessment, vitals)

        # Extract from clinical notes
        notes = clinical_data.get('notes', [])
        self._extract_from_notes(assessment, notes)

        # Extract prior interventions from surgical history
        surgeries = clinical_data.get('surgical_history', [])
        self._extract_prior_interventions(assessment, surgeries)

        # Classify Rutherford
        self._classify_rutherford(assessment)

        logger.info(f"[PAD] Extracted assessment for patient {patient_id}: Rutherford {assessment.rutherford_class}")
        return assessment

    def _extract_from_problems(self, assessment: PADAssessment, problems: List[Dict]) -> None:
        """Extract PAD indicators from problem list."""
        for prob in problems:
            name = prob.get('name', '').lower()
            icd = prob.get('icd10_code', '').upper()

            # Check for PAD diagnosis
            if any(kw in name for kw in ['peripheral arterial', 'peripheral vascular', 'pad', 'pvd']):
                assessment.affected_segments.append('PAD diagnosed')

            # Check ICD-10 codes
            if icd.startswith('I70.2'):  # Atherosclerosis of native arteries of extremities
                assessment.affected_segments.append(f'PAD ({icd})')
            if icd.startswith('I70.3'):  # Atherosclerosis of bypass graft
                assessment.prior_bypass.append(f'Prior bypass (from {icd})')

            # Claudication
            if 'claudication' in name or icd in ['I70.211', 'I70.212', 'I70.213', 'I70.218', 'I70.219']:
                assessment.has_claudication = True

            # Rest pain
            if 'rest pain' in name or icd in ['I70.221', 'I70.222', 'I70.223', 'I70.228', 'I70.229']:
                assessment.rest_pain = True

            # Ulceration/gangrene
            if any(kw in name for kw in ['ulcer', 'gangrene', 'necrosis']):
                if 'gangrene' in name:
                    assessment.gangrene = True
                else:
                    assessment.tissue_loss = True
            if icd.startswith('I70.23') or icd.startswith('I70.24') or icd.startswith('I70.25'):
                assessment.tissue_loss = True
            if icd.startswith('I70.26'):
                assessment.gangrene = True

    def _extract_abi_from_vitals(self, assessment: PADAssessment, vitals: List[Dict]) -> None:
        """Extract ABI readings from vital signs."""
        for vital in vitals:
            name = vital.get('name', '').lower()
            value = vital.get('value')

            if 'abi' in name or 'ankle brachial' in name:
                try:
                    abi_val = float(value)
                    side = 'left' if 'left' in name or 'l ' in name else 'right'
                    assessment.abi_readings.append(ABIReading(
                        side=side,
                        value=abi_val,
                        date=vital.get('date')
                    ))
                except (ValueError, TypeError):
                    pass

            if 'tbi' in name or 'toe brachial' in name:
                try:
                    tbi_val = float(value)
                    side = 'left' if 'left' in name else 'right'
                    assessment.tbi_readings.append(TBIReading(
                        side=side,
                        value=tbi_val,
                        date=vital.get('date')
                    ))
                except (ValueError, TypeError):
                    pass

    def _extract_from_notes(self, assessment: PADAssessment, notes: List[Dict]) -> None:
        """Extract PAD data from clinical notes."""
        for note in notes:
            text = note.get('text', '').lower()

            # Check for claudication
            if any(kw in text for kw in self.CLAUDICATION_KEYWORDS):
                assessment.has_claudication = True
                # Try to extract walking distance
                dist_match = re.search(r'(\d+)\s*(meters?|feet|blocks?|yards?)', text)
                if dist_match:
                    dist = int(dist_match.group(1))
                    unit = dist_match.group(2)
                    if 'feet' in unit:
                        dist = int(dist * 0.3048)
                    elif 'block' in unit:
                        dist = dist * 100  # Approximate
                    elif 'yard' in unit:
                        dist = int(dist * 0.9144)
                    assessment.claudication_distance_meters = dist

            # Check for rest pain
            if any(kw in text for kw in self.REST_PAIN_KEYWORDS):
                assessment.rest_pain = True

            # Check for tissue loss
            if any(kw in text for kw in self.TISSUE_LOSS_KEYWORDS):
                if 'gangrene' in text:
                    assessment.gangrene = True
                else:
                    assessment.tissue_loss = True

            # Extract ABI values from notes
            abi_matches = re.findall(r'abi[:\s]*(\d+\.?\d*)', text)
            for match in abi_matches:
                try:
                    val = float(match)
                    if 0.1 < val < 2.0:  # Sanity check
                        assessment.abi_readings.append(ABIReading(
                            side='unknown',
                            value=val,
                            date=note.get('date')
                        ))
                except ValueError:
                    pass

            # Extract affected segments
            for segment, pattern in self.SEGMENT_PATTERNS.items():
                if re.search(pattern, text, re.IGNORECASE):
                    if 'occlu' in text or 'total occlusion' in text:
                        assessment.occlusions.append(segment)
                    elif 'steno' in text:
                        assessment.affected_segments.append(segment)

    def _extract_prior_interventions(self, assessment: PADAssessment, surgeries: List[Dict]) -> None:
        """Extract prior vascular interventions from surgical history."""
        bypass_keywords = ['bypass', 'fem-pop', 'fem-tib', 'aortobifemoral', 'axillofemoral']
        pta_keywords = ['angioplasty', 'pta', 'balloon', 'percutaneous']
        stent_keywords = ['stent', 'covered stent', 'viabahn']
        amputation_keywords = ['amputation', 'bka', 'aka', 'toe amputation', 'tma']

        for surg in surgeries:
            proc = surg.get('procedure', '').lower()
            date_str = surg.get('date', '')

            if any(kw in proc for kw in bypass_keywords):
                assessment.prior_bypass.append(f"{proc} ({date_str})")
            if any(kw in proc for kw in pta_keywords):
                assessment.prior_angioplasty.append(f"{proc} ({date_str})")
            if any(kw in proc for kw in stent_keywords):
                assessment.prior_stents.append(f"{proc} ({date_str})")
            if any(kw in proc for kw in amputation_keywords):
                assessment.prior_amputation = f"{proc} ({date_str})"

    def _classify_rutherford(self, assessment: PADAssessment) -> None:
        """Determine Rutherford classification."""
        if assessment.gangrene:
            assessment.rutherford_class = 6
        elif assessment.tissue_loss:
            assessment.rutherford_class = 5
        elif assessment.rest_pain:
            assessment.rutherford_class = 4
        elif assessment.has_claudication:
            if assessment.claudication_distance_meters:
                if assessment.claudication_distance_meters < 100:
                    assessment.rutherford_class = 3
                elif assessment.claudication_distance_meters < 200:
                    assessment.rutherford_class = 2
                else:
                    assessment.rutherford_class = 1
            else:
                assessment.rutherford_class = 2  # Default moderate
        else:
            assessment.rutherford_class = 0


# ==============================================================================
# CAROTID DISEASE EXTRACTOR
# ==============================================================================

@dataclass
class CarotidAssessment:
    """Complete carotid disease assessment."""
    patient_id: str
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Stenosis measurements
    right_stenosis_percent: Optional[int] = None
    left_stenosis_percent: Optional[int] = None
    measurement_method: Optional[str] = None  # "duplex", "CTA", "MRA", "angiography"
    measurement_date: Optional[str] = None

    # Symptom status
    symptom_status: CarotidSymptomStatus = CarotidSymptomStatus.UNKNOWN
    symptom_side: Optional[str] = None  # "left", "right", "bilateral"
    last_symptom_date: Optional[str] = None
    days_since_symptom: Optional[int] = None

    # Plaque characteristics
    plaque_ulcerated: bool = False
    plaque_calcified: bool = False
    plaque_echolucent: bool = False  # "soft" plaque - higher risk

    # Contralateral disease
    contralateral_occlusion: bool = False
    contralateral_stenosis_percent: Optional[int] = None

    # Prior interventions
    prior_cea: List[str] = field(default_factory=list)
    prior_cas: List[str] = field(default_factory=list)

    # Additional findings
    intracranial_disease: bool = False
    tandem_lesions: bool = False

    def dominant_stenosis(self) -> Tuple[str, int]:
        """Get the side and value of worst stenosis."""
        left = self.left_stenosis_percent or 0
        right = self.right_stenosis_percent or 0
        if left >= right:
            return ("left", left)
        return ("right", right)

    def intervention_indicated(self) -> Tuple[bool, str]:
        """
        Determine if intervention is indicated based on guidelines.

        Returns (indicated, reason)
        """
        side, stenosis = self.dominant_stenosis()

        if self.symptom_status in [CarotidSymptomStatus.SYMPTOMATIC_TIA,
                                    CarotidSymptomStatus.SYMPTOMATIC_STROKE,
                                    CarotidSymptomStatus.SYMPTOMATIC_AMAUROSIS]:
            # Symptomatic thresholds
            if stenosis >= 50:
                urgency = "URGENT" if self.days_since_symptom and self.days_since_symptom <= 14 else "indicated"
                return (True, f"Symptomatic {stenosis}% stenosis - {urgency}")
        else:
            # Asymptomatic thresholds
            if stenosis >= 70:
                return (True, f"Asymptomatic {stenosis}% stenosis - consider intervention")
            elif stenosis >= 60 and (self.plaque_ulcerated or self.plaque_echolucent):
                return (True, f"Asymptomatic {stenosis}% with high-risk plaque features")

        return (False, f"{stenosis}% stenosis - medical management")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        indicated, reason = self.intervention_indicated()
        return {
            "patient_id": self.patient_id,
            "assessed_at": self.assessed_at,
            "right_stenosis_percent": self.right_stenosis_percent,
            "left_stenosis_percent": self.left_stenosis_percent,
            "dominant_stenosis": {"side": self.dominant_stenosis()[0], "percent": self.dominant_stenosis()[1]},
            "measurement_method": self.measurement_method,
            "symptom_status": self.symptom_status.value,
            "symptom_side": self.symptom_side,
            "days_since_symptom": self.days_since_symptom,
            "plaque_characteristics": {
                "ulcerated": self.plaque_ulcerated,
                "calcified": self.plaque_calcified,
                "echolucent": self.plaque_echolucent,
            },
            "contralateral_occlusion": self.contralateral_occlusion,
            "prior_interventions": {
                "cea": self.prior_cea,
                "cas": self.prior_cas,
            },
            "intervention_indicated": indicated,
            "recommendation": reason,
        }


class CarotidExtractor:
    """Extracts carotid disease data from clinical records."""

    SYMPTOM_KEYWORDS = {
        'tia': CarotidSymptomStatus.SYMPTOMATIC_TIA,
        'transient ischemic': CarotidSymptomStatus.SYMPTOMATIC_TIA,
        'stroke': CarotidSymptomStatus.SYMPTOMATIC_STROKE,
        'cva': CarotidSymptomStatus.SYMPTOMATIC_STROKE,
        'cerebrovascular accident': CarotidSymptomStatus.SYMPTOMATIC_STROKE,
        'amaurosis': CarotidSymptomStatus.SYMPTOMATIC_AMAUROSIS,
        'amaurosis fugax': CarotidSymptomStatus.SYMPTOMATIC_AMAUROSIS,
        'transient monocular': CarotidSymptomStatus.SYMPTOMATIC_AMAUROSIS,
    }

    def extract(self, patient_id: str, clinical_data: Dict[str, Any]) -> CarotidAssessment:
        """Extract carotid assessment from clinical data."""
        assessment = CarotidAssessment(patient_id=patient_id)

        # Extract from problems/diagnoses
        problems = clinical_data.get('problems', [])
        self._extract_from_problems(assessment, problems)

        # Extract from imaging/test results
        results = clinical_data.get('results', []) + clinical_data.get('imaging', [])
        self._extract_from_results(assessment, results)

        # Extract from clinical notes
        notes = clinical_data.get('notes', [])
        self._extract_from_notes(assessment, notes)

        # Extract prior interventions
        surgeries = clinical_data.get('surgical_history', [])
        self._extract_prior_interventions(assessment, surgeries)

        logger.info(f"[CAROTID] Extracted assessment for patient {patient_id}: "
                   f"{assessment.dominant_stenosis()[1]}% stenosis, {assessment.symptom_status.value}")
        return assessment

    def _extract_from_problems(self, assessment: CarotidAssessment, problems: List[Dict]) -> None:
        """Extract carotid indicators from problem list."""
        for prob in problems:
            name = prob.get('name', '').lower()
            icd = prob.get('icd10_code', '').upper()

            # Carotid stenosis diagnosis
            if 'carotid' in name and 'stenosis' in name:
                # Try to extract percentage
                pct_match = re.search(r'(\d+)\s*%', name)
                if pct_match:
                    pct = int(pct_match.group(1))
                    if 'left' in name:
                        assessment.left_stenosis_percent = pct
                    elif 'right' in name:
                        assessment.right_stenosis_percent = pct

            # ICD-10 codes for carotid disease
            if icd.startswith('I65.2'):  # Carotid artery occlusion/stenosis
                pass  # Diagnosis confirmed

            # Check for symptoms
            for keyword, status in self.SYMPTOM_KEYWORDS.items():
                if keyword in name:
                    assessment.symptom_status = status
                    if 'left' in name:
                        assessment.symptom_side = 'left'
                    elif 'right' in name:
                        assessment.symptom_side = 'right'

    def _extract_from_results(self, assessment: CarotidAssessment, results: List[Dict]) -> None:
        """Extract stenosis values from imaging results."""
        for result in results:
            name = result.get('name', '').lower()
            text = result.get('text', '').lower()

            if 'carotid' in name or 'carotid' in text:
                # Determine imaging modality
                if 'duplex' in name or 'ultrasound' in name:
                    assessment.measurement_method = 'duplex'
                elif 'cta' in name or 'ct angio' in name:
                    assessment.measurement_method = 'CTA'
                elif 'mra' in name or 'mr angio' in name:
                    assessment.measurement_method = 'MRA'

                # Extract stenosis percentages
                # Pattern: "right ICA 70% stenosis" or "70-79% stenosis"
                right_match = re.search(r'right.{0,30}(\d+)[\s\-]*(?:\d+)?%', text)
                left_match = re.search(r'left.{0,30}(\d+)[\s\-]*(?:\d+)?%', text)

                if right_match:
                    assessment.right_stenosis_percent = int(right_match.group(1))
                if left_match:
                    assessment.left_stenosis_percent = int(left_match.group(1))

                # Check for occlusion
                if 'occlu' in text:
                    if 'right' in text and 'occlu' in text[text.find('right'):text.find('right')+50]:
                        assessment.right_stenosis_percent = 100
                    if 'left' in text and 'occlu' in text[text.find('left'):text.find('left')+50]:
                        assessment.left_stenosis_percent = 100

                # Plaque characteristics
                if 'ulcerat' in text:
                    assessment.plaque_ulcerated = True
                if 'calcif' in text:
                    assessment.plaque_calcified = True
                if 'echolucent' in text or 'soft plaque' in text or 'hypoechoic' in text:
                    assessment.plaque_echolucent = True

                assessment.measurement_date = result.get('date')

    def _extract_from_notes(self, assessment: CarotidAssessment, notes: List[Dict]) -> None:
        """Extract carotid data from clinical notes."""
        for note in notes:
            text = note.get('text', '').lower()

            # Check for symptoms
            for keyword, status in self.SYMPTOM_KEYWORDS.items():
                if keyword in text:
                    assessment.symptom_status = status

            # Check for contralateral occlusion
            if 'contralateral' in text and 'occlu' in text:
                assessment.contralateral_occlusion = True

    def _extract_prior_interventions(self, assessment: CarotidAssessment, surgeries: List[Dict]) -> None:
        """Extract prior CEA/CAS from surgical history."""
        for surg in surgeries:
            proc = surg.get('procedure', '').lower()
            date_str = surg.get('date', '')

            if 'endarterectomy' in proc or 'cea' in proc:
                assessment.prior_cea.append(f"{proc} ({date_str})")
            if 'carotid stent' in proc or 'cas' in proc:
                assessment.prior_cas.append(f"{proc} ({date_str})")


# ==============================================================================
# AAA (ABDOMINAL AORTIC ANEURYSM) EXTRACTOR
# ==============================================================================

@dataclass
class AAAMeasurement:
    """Single AAA diameter measurement."""
    diameter_cm: float
    date: str
    modality: Optional[str] = None  # "CT", "ultrasound", "MRI"

    @property
    def rupture_risk_category(self) -> AneurysmRuptureRisk:
        """Estimate annual rupture risk category."""
        if self.diameter_cm < 4.0:
            return AneurysmRuptureRisk.LOW
        elif self.diameter_cm < 5.5:
            return AneurysmRuptureRisk.MODERATE
        elif self.diameter_cm < 6.0:
            return AneurysmRuptureRisk.HIGH
        else:
            return AneurysmRuptureRisk.VERY_HIGH

    @property
    def annual_rupture_risk_percent(self) -> str:
        """Estimate annual rupture risk percentage."""
        if self.diameter_cm < 4.0:
            return "<0.5%"
        elif self.diameter_cm < 5.0:
            return "0.5-5%"
        elif self.diameter_cm < 6.0:
            return "3-15%"
        elif self.diameter_cm < 7.0:
            return "10-20%"
        else:
            return "20-40%"


@dataclass
class AAAAssessment:
    """Complete AAA assessment."""
    patient_id: str
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Measurements
    measurements: List[AAAMeasurement] = field(default_factory=list)

    # Anatomic details
    infrarenal: bool = True
    juxtarenal: bool = False
    suprarenal: bool = False
    neck_length_mm: Optional[int] = None
    neck_angle_degrees: Optional[int] = None
    neck_diameter_mm: Optional[int] = None

    # Iliac involvement
    right_iliac_diameter_mm: Optional[int] = None
    left_iliac_diameter_mm: Optional[int] = None
    iliac_aneurysm: bool = False

    # EVAR suitability factors
    access_vessels_suitable: bool = True
    excessive_thrombus: bool = False
    excessive_calcification: bool = False

    # Prior repair
    prior_repair: Optional[str] = None  # "EVAR 2020", "Open repair 2018"
    endoleak: Optional[str] = None  # "Type II endoleak"

    # Symptoms
    symptomatic: bool = False
    ruptured: bool = False

    def current_diameter(self) -> Optional[float]:
        """Get most recent diameter measurement."""
        if not self.measurements:
            return None
        # Sort by date descending
        sorted_meas = sorted(self.measurements, key=lambda x: x.date, reverse=True)
        return sorted_meas[0].diameter_cm

    def growth_rate_cm_per_year(self) -> Optional[float]:
        """Calculate growth rate if multiple measurements exist."""
        if len(self.measurements) < 2:
            return None

        sorted_meas = sorted(self.measurements, key=lambda x: x.date)
        first = sorted_meas[0]
        last = sorted_meas[-1]

        try:
            from datetime import datetime
            d1 = datetime.fromisoformat(first.date.replace('Z', '+00:00'))
            d2 = datetime.fromisoformat(last.date.replace('Z', '+00:00'))
            days = (d2 - d1).days
            if days > 0:
                years = days / 365.25
                growth = last.diameter_cm - first.diameter_cm
                return round(growth / years, 2)
        except Exception:
            pass
        return None

    def repair_indicated(self) -> Tuple[bool, str]:
        """Determine if repair is indicated."""
        diameter = self.current_diameter()
        if diameter is None:
            return (False, "No measurements available")

        if self.ruptured:
            return (True, "EMERGENT - Ruptured AAA")

        if self.symptomatic:
            return (True, "URGENT - Symptomatic AAA")

        growth = self.growth_rate_cm_per_year()
        rapid_growth = growth and growth > 1.0

        if diameter >= 5.5:
            return (True, f"{diameter}cm - Exceeds repair threshold")

        if diameter >= 5.0 and rapid_growth:
            return (True, f"{diameter}cm with rapid growth ({growth}cm/yr)")

        if 5.0 <= diameter < 5.5:
            return (True, f"{diameter}cm - At repair threshold (female) or approaching (male)")

        return (False, f"{diameter}cm - Surveillance recommended")

    def evar_suitability(self) -> EVARSuitability:
        """Assess EVAR anatomic suitability."""
        if self.suprarenal or self.juxtarenal:
            return EVARSuitability.UNSUITABLE

        issues = 0
        if self.neck_length_mm and self.neck_length_mm < 15:
            issues += 1
        if self.neck_angle_degrees and self.neck_angle_degrees > 60:
            issues += 1
        if self.excessive_thrombus:
            issues += 1
        if self.excessive_calcification:
            issues += 1
        if not self.access_vessels_suitable:
            issues += 1

        if issues == 0:
            return EVARSuitability.SUITABLE
        elif issues <= 2:
            return EVARSuitability.CHALLENGING
        else:
            return EVARSuitability.UNSUITABLE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        current = self.current_diameter()
        indicated, reason = self.repair_indicated()

        return {
            "patient_id": self.patient_id,
            "assessed_at": self.assessed_at,
            "current_diameter_cm": current,
            "measurements": [{"diameter_cm": m.diameter_cm, "date": m.date, "modality": m.modality,
                             "rupture_risk": m.annual_rupture_risk_percent} for m in self.measurements],
            "growth_rate_cm_per_year": self.growth_rate_cm_per_year(),
            "anatomy": {
                "infrarenal": self.infrarenal,
                "juxtarenal": self.juxtarenal,
                "suprarenal": self.suprarenal,
                "neck_length_mm": self.neck_length_mm,
                "neck_angle_degrees": self.neck_angle_degrees,
            },
            "iliac_involvement": {
                "right_diameter_mm": self.right_iliac_diameter_mm,
                "left_diameter_mm": self.left_iliac_diameter_mm,
                "iliac_aneurysm": self.iliac_aneurysm,
            },
            "evar_suitability": self.evar_suitability().value,
            "symptomatic": self.symptomatic,
            "ruptured": self.ruptured,
            "prior_repair": self.prior_repair,
            "repair_indicated": indicated,
            "recommendation": reason,
        }


class AAAExtractor:
    """Extracts AAA-specific data from clinical records."""

    def extract(self, patient_id: str, clinical_data: Dict[str, Any]) -> AAAAssessment:
        """Extract AAA assessment from clinical data."""
        assessment = AAAAssessment(patient_id=patient_id)

        # Extract from problems/diagnoses
        problems = clinical_data.get('problems', [])
        self._extract_from_problems(assessment, problems)

        # Extract from imaging results
        results = clinical_data.get('results', []) + clinical_data.get('imaging', [])
        self._extract_from_imaging(assessment, results)

        # Extract from notes
        notes = clinical_data.get('notes', [])
        self._extract_from_notes(assessment, notes)

        # Extract prior repairs
        surgeries = clinical_data.get('surgical_history', [])
        self._extract_prior_repairs(assessment, surgeries)

        logger.info(f"[AAA] Extracted assessment for patient {patient_id}: "
                   f"{assessment.current_diameter()}cm")
        return assessment

    def _extract_from_problems(self, assessment: AAAAssessment, problems: List[Dict]) -> None:
        """Extract AAA indicators from problem list."""
        for prob in problems:
            name = prob.get('name', '').lower()
            icd = prob.get('icd10_code', '').upper()

            # AAA diagnosis
            if 'abdominal' in name and 'aneurysm' in name:
                # Try to extract size
                size_match = re.search(r'(\d+\.?\d*)\s*(cm|mm)', name)
                if size_match:
                    size = float(size_match.group(1))
                    unit = size_match.group(2)
                    if unit == 'mm':
                        size = size / 10
                    assessment.measurements.append(AAAMeasurement(
                        diameter_cm=size,
                        date=prob.get('onset_date', datetime.utcnow().isoformat())
                    ))

            # ICD-10 codes
            if icd.startswith('I71.4'):  # AAA without rupture
                pass
            if icd.startswith('I71.3'):  # AAA ruptured
                assessment.ruptured = True

            # Iliac aneurysm
            if 'iliac' in name and 'aneurysm' in name:
                assessment.iliac_aneurysm = True

    def _extract_from_imaging(self, assessment: AAAAssessment, results: List[Dict]) -> None:
        """Extract measurements from imaging results."""
        for result in results:
            name = result.get('name', '').lower()
            text = result.get('text', '').lower()

            if 'aort' in name or 'aort' in text:
                # Determine modality
                modality = None
                if 'ct' in name:
                    modality = 'CT'
                elif 'ultrasound' in name or 'us' in name:
                    modality = 'ultrasound'
                elif 'mri' in name or 'mr' in name:
                    modality = 'MRI'

                # Extract diameter
                # Patterns: "5.2 cm", "5.2cm", "52mm"
                diam_match = re.search(r'(?:aort|infrarenal|aneurysm).{0,50}?(\d+\.?\d*)\s*(cm|mm)', text)
                if diam_match:
                    size = float(diam_match.group(1))
                    unit = diam_match.group(2)
                    if unit == 'mm':
                        size = size / 10
                    if 2.0 < size < 15.0:  # Sanity check
                        assessment.measurements.append(AAAMeasurement(
                            diameter_cm=size,
                            date=result.get('date', datetime.utcnow().isoformat()),
                            modality=modality
                        ))

                # Extract neck length
                neck_match = re.search(r'neck.{0,20}?(\d+)\s*mm', text)
                if neck_match:
                    assessment.neck_length_mm = int(neck_match.group(1))

                # Check anatomy
                if 'juxtarenal' in text:
                    assessment.juxtarenal = True
                    assessment.infrarenal = False
                if 'suprarenal' in text or 'pararenal' in text:
                    assessment.suprarenal = True
                    assessment.infrarenal = False

                # Check iliac
                iliac_match = re.search(r'(right|left)\s*iliac.{0,30}?(\d+)\s*mm', text)
                if iliac_match:
                    side = iliac_match.group(1)
                    diam = int(iliac_match.group(2))
                    if side == 'right':
                        assessment.right_iliac_diameter_mm = diam
                    else:
                        assessment.left_iliac_diameter_mm = diam
                    if diam > 18:  # >1.8cm = aneurysmal
                        assessment.iliac_aneurysm = True

    def _extract_from_notes(self, assessment: AAAAssessment, notes: List[Dict]) -> None:
        """Extract AAA data from clinical notes."""
        for note in notes:
            text = note.get('text', '').lower()

            if 'symptomatic' in text and 'aneurysm' in text:
                assessment.symptomatic = True

            if 'rupture' in text and 'aneurysm' in text:
                assessment.ruptured = True

    def _extract_prior_repairs(self, assessment: AAAAssessment, surgeries: List[Dict]) -> None:
        """Extract prior AAA repairs from surgical history."""
        for surg in surgeries:
            proc = surg.get('procedure', '').lower()
            date_str = surg.get('date', '')

            if 'evar' in proc or 'endovascular' in proc and 'aneurysm' in proc:
                assessment.prior_repair = f"EVAR ({date_str})"
            elif 'open' in proc and ('aaa' in proc or 'aneurysm' in proc):
                assessment.prior_repair = f"Open repair ({date_str})"


# ==============================================================================
# ANTITHROMBOTIC BRIDGING MODULE
# ==============================================================================

@dataclass
class AntithromboticMedication:
    """Antithrombotic medication with bridging parameters."""
    name: str
    drug_class: str  # "antiplatelet", "anticoagulant", "direct_anticoagulant"
    hold_days_before: int
    restart_days_after: int
    half_life_hours: Optional[float] = None
    reversible: bool = False
    reversal_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "drug_class": self.drug_class,
            "hold_days_before": self.hold_days_before,
            "restart_days_after": self.restart_days_after,
            "half_life_hours": self.half_life_hours,
            "reversible": self.reversible,
            "reversal_agent": self.reversal_agent,
        }


# Standard antithrombotic bridging parameters
ANTITHROMBOTIC_DATABASE: Dict[str, AntithromboticMedication] = {
    # Antiplatelets
    'aspirin': AntithromboticMedication(
        name='Aspirin', drug_class='antiplatelet',
        hold_days_before=0,  # Often continued for vascular surgery
        restart_days_after=0,
        reversible=False
    ),
    'clopidogrel': AntithromboticMedication(
        name='Clopidogrel (Plavix)', drug_class='antiplatelet',
        hold_days_before=5,
        restart_days_after=1,
        half_life_hours=6,
        reversible=False
    ),
    'plavix': AntithromboticMedication(
        name='Clopidogrel (Plavix)', drug_class='antiplatelet',
        hold_days_before=5,
        restart_days_after=1,
        half_life_hours=6,
        reversible=False
    ),
    'ticagrelor': AntithromboticMedication(
        name='Ticagrelor (Brilinta)', drug_class='antiplatelet',
        hold_days_before=5,
        restart_days_after=1,
        half_life_hours=7,
        reversible=True  # Partially reversible
    ),
    'prasugrel': AntithromboticMedication(
        name='Prasugrel (Effient)', drug_class='antiplatelet',
        hold_days_before=7,
        restart_days_after=1,
        half_life_hours=7,
        reversible=False
    ),

    # Vitamin K Antagonists
    'warfarin': AntithromboticMedication(
        name='Warfarin (Coumadin)', drug_class='anticoagulant',
        hold_days_before=5,
        restart_days_after=1,  # When hemostasis achieved
        half_life_hours=40,
        reversible=True,
        reversal_agent='Vitamin K, FFP, PCC'
    ),
    'coumadin': AntithromboticMedication(
        name='Warfarin (Coumadin)', drug_class='anticoagulant',
        hold_days_before=5,
        restart_days_after=1,
        half_life_hours=40,
        reversible=True,
        reversal_agent='Vitamin K, FFP, PCC'
    ),

    # Direct Oral Anticoagulants (DOACs)
    'rivaroxaban': AntithromboticMedication(
        name='Rivaroxaban (Xarelto)', drug_class='direct_anticoagulant',
        hold_days_before=2,  # 48 hours for normal renal function
        restart_days_after=1,
        half_life_hours=9,
        reversible=True,
        reversal_agent='Andexanet alfa'
    ),
    'xarelto': AntithromboticMedication(
        name='Rivaroxaban (Xarelto)', drug_class='direct_anticoagulant',
        hold_days_before=2,
        restart_days_after=1,
        half_life_hours=9,
        reversible=True,
        reversal_agent='Andexanet alfa'
    ),
    'apixaban': AntithromboticMedication(
        name='Apixaban (Eliquis)', drug_class='direct_anticoagulant',
        hold_days_before=2,
        restart_days_after=1,
        half_life_hours=12,
        reversible=True,
        reversal_agent='Andexanet alfa'
    ),
    'eliquis': AntithromboticMedication(
        name='Apixaban (Eliquis)', drug_class='direct_anticoagulant',
        hold_days_before=2,
        restart_days_after=1,
        half_life_hours=12,
        reversible=True,
        reversal_agent='Andexanet alfa'
    ),
    'dabigatran': AntithromboticMedication(
        name='Dabigatran (Pradaxa)', drug_class='direct_anticoagulant',
        hold_days_before=2,  # Longer if CrCl <50
        restart_days_after=1,
        half_life_hours=14,
        reversible=True,
        reversal_agent='Idarucizumab (Praxbind)'
    ),
    'pradaxa': AntithromboticMedication(
        name='Dabigatran (Pradaxa)', drug_class='direct_anticoagulant',
        hold_days_before=2,
        restart_days_after=1,
        half_life_hours=14,
        reversible=True,
        reversal_agent='Idarucizumab (Praxbind)'
    ),
    'edoxaban': AntithromboticMedication(
        name='Edoxaban (Savaysa)', drug_class='direct_anticoagulant',
        hold_days_before=2,
        restart_days_after=1,
        half_life_hours=11,
        reversible=True,
        reversal_agent='Andexanet alfa'
    ),

    # Parenteral anticoagulants
    'heparin': AntithromboticMedication(
        name='Heparin (UFH)', drug_class='anticoagulant',
        hold_days_before=0,  # Stop 4-6 hours before
        restart_days_after=0,
        half_life_hours=1.5,
        reversible=True,
        reversal_agent='Protamine'
    ),
    'enoxaparin': AntithromboticMedication(
        name='Enoxaparin (Lovenox)', drug_class='anticoagulant',
        hold_days_before=1,  # 24 hours
        restart_days_after=1,
        half_life_hours=4.5,
        reversible=True,
        reversal_agent='Protamine (partial)'
    ),
    'lovenox': AntithromboticMedication(
        name='Enoxaparin (Lovenox)', drug_class='anticoagulant',
        hold_days_before=1,
        restart_days_after=1,
        half_life_hours=4.5,
        reversible=True,
        reversal_agent='Protamine (partial)'
    ),
}


@dataclass
class BridgingRecommendation:
    """Perioperative antithrombotic management recommendation."""
    medication: AntithromboticMedication
    current_dose: Optional[str] = None
    indication: Optional[str] = None  # Why patient is on this med

    # Recommendations
    hold_recommended: bool = True
    hold_days: int = 0
    restart_day: int = 1
    bridge_recommended: bool = False
    bridge_regimen: Optional[str] = None

    # Risk factors
    high_thrombotic_risk: bool = False
    thrombotic_risk_reason: Optional[str] = None
    high_bleeding_risk: bool = False
    bleeding_risk_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "medication": self.medication.to_dict(),
            "current_dose": self.current_dose,
            "indication": self.indication,
            "hold_recommended": self.hold_recommended,
            "hold_days_before_surgery": self.hold_days,
            "restart_postop_day": self.restart_day,
            "bridge_recommended": self.bridge_recommended,
            "bridge_regimen": self.bridge_regimen,
            "high_thrombotic_risk": self.high_thrombotic_risk,
            "thrombotic_risk_reason": self.thrombotic_risk_reason,
            "high_bleeding_risk": self.high_bleeding_risk,
            "bleeding_risk_reason": self.bleeding_risk_reason,
        }


@dataclass
class BridgingPlan:
    """Complete perioperative antithrombotic bridging plan."""
    patient_id: str
    surgery_date: Optional[str] = None
    procedure_type: Optional[str] = None
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Risk scores
    chadsvasc_score: Optional[int] = None  # For AFib patients
    hasbled_score: Optional[int] = None

    # Recommendations
    recommendations: List[BridgingRecommendation] = field(default_factory=list)

    # Summary
    aspirin_continue: bool = True  # Typically continued for vascular
    needs_bridging: bool = False
    bridge_start_date: Optional[str] = None
    bridge_stop_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "surgery_date": self.surgery_date,
            "procedure_type": self.procedure_type,
            "assessed_at": self.assessed_at,
            "chadsvasc_score": self.chadsvasc_score,
            "hasbled_score": self.hasbled_score,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "aspirin_continue": self.aspirin_continue,
            "needs_bridging": self.needs_bridging,
            "summary": self._generate_summary(),
        }

    def _generate_summary(self) -> str:
        """Generate human-readable bridging summary."""
        lines = []

        for rec in self.recommendations:
            if rec.hold_recommended:
                lines.append(f"- HOLD {rec.medication.name} {rec.hold_days} days before surgery")
                if rec.bridge_recommended:
                    lines.append(f"  → BRIDGE with {rec.bridge_regimen}")
                lines.append(f"  → RESTART POD {rec.restart_day} when hemostasis achieved")
            else:
                lines.append(f"- CONTINUE {rec.medication.name}")

        if not lines:
            return "No antithrombotic medications identified"

        return "\n".join(lines)


class AntithromboticBridgingCalculator:
    """Calculates perioperative antithrombotic bridging recommendations."""

    # High thrombotic risk indications for warfarin bridging
    HIGH_RISK_INDICATIONS = [
        'mechanical valve', 'mitral valve', 'afib', 'atrial fibrillation',
        'dvt', 'pe', 'pulmonary embolism', 'deep vein thrombosis',
        'stroke', 'tia', 'recent stent'
    ]

    def calculate_bridging_plan(
        self,
        patient_id: str,
        medications: List[Dict],
        problems: List[Dict],
        surgery_type: str = "vascular",
        surgery_date: Optional[str] = None
    ) -> BridgingPlan:
        """
        Calculate complete bridging plan.

        Args:
            patient_id: Patient identifier
            medications: List of current medications
            problems: List of diagnoses/problems
            surgery_type: Type of surgery for bleeding risk assessment
            surgery_date: Planned surgery date

        Returns:
            BridgingPlan with recommendations for each antithrombotic
        """
        plan = BridgingPlan(
            patient_id=patient_id,
            surgery_date=surgery_date,
            procedure_type=surgery_type
        )

        # Calculate CHA2DS2-VASc if AFib present
        if self._has_afib(problems):
            plan.chadsvasc_score = self._calculate_chadsvasc(problems)

        # Process each medication
        for med in medications:
            med_name = med.get('name', '').lower()

            # Check against antithrombotic database
            for key, at_med in ANTITHROMBOTIC_DATABASE.items():
                if key in med_name:
                    rec = self._create_recommendation(
                        at_med,
                        med,
                        problems,
                        surgery_type,
                        plan.chadsvasc_score
                    )
                    plan.recommendations.append(rec)

                    if rec.bridge_recommended:
                        plan.needs_bridging = True
                    break

        # Aspirin handling for vascular surgery
        aspirin_rec = next((r for r in plan.recommendations if 'aspirin' in r.medication.name.lower()), None)
        if aspirin_rec:
            if surgery_type == 'vascular':
                aspirin_rec.hold_recommended = False  # Continue for vascular
                plan.aspirin_continue = True

        logger.info(f"[BRIDGING] Created plan for patient {patient_id}: "
                   f"{len(plan.recommendations)} medications, bridging={'yes' if plan.needs_bridging else 'no'}")
        return plan

    def _create_recommendation(
        self,
        at_med: AntithromboticMedication,
        med_record: Dict,
        problems: List[Dict],
        surgery_type: str,
        chadsvasc: Optional[int]
    ) -> BridgingRecommendation:
        """Create bridging recommendation for a single medication."""
        rec = BridgingRecommendation(
            medication=at_med,
            current_dose=med_record.get('dose') or med_record.get('sig'),
            hold_recommended=True,
            hold_days=at_med.hold_days_before,
            restart_day=at_med.restart_days_after
        )

        # Determine indication
        rec.indication = self._find_indication(at_med, problems)

        # Assess thrombotic risk
        rec.high_thrombotic_risk, rec.thrombotic_risk_reason = self._assess_thrombotic_risk(
            at_med, problems, chadsvasc
        )

        # Assess bleeding risk
        rec.high_bleeding_risk, rec.bleeding_risk_reason = self._assess_bleeding_risk(
            surgery_type, problems
        )

        # Determine if bridging needed (warfarin patients)
        if at_med.drug_class == 'anticoagulant' and 'warfarin' in at_med.name.lower():
            if rec.high_thrombotic_risk and not rec.high_bleeding_risk:
                rec.bridge_recommended = True
                rec.bridge_regimen = "Enoxaparin 1mg/kg BID, start 3 days before, hold 24h pre-op"

        # Adjust hold time for renal impairment (DOACs)
        if at_med.drug_class == 'direct_anticoagulant':
            if self._has_ckd(problems):
                rec.hold_days = at_med.hold_days_before + 1
                rec.bridge_regimen = f"Extended hold ({rec.hold_days} days) due to CKD"

        return rec

    def _find_indication(self, at_med: AntithromboticMedication, problems: List[Dict]) -> Optional[str]:
        """Find likely indication for the antithrombotic."""
        problem_text = ' '.join(p.get('name', '').lower() for p in problems)

        if at_med.drug_class in ['anticoagulant', 'direct_anticoagulant']:
            if 'atrial fibrillation' in problem_text or 'afib' in problem_text:
                return "Atrial fibrillation"
            if 'dvt' in problem_text or 'deep vein' in problem_text:
                return "DVT"
            if 'pulmonary embolism' in problem_text or ' pe ' in problem_text:
                return "Pulmonary embolism"
            if 'mechanical valve' in problem_text:
                return "Mechanical heart valve"
        elif at_med.drug_class == 'antiplatelet':
            if 'coronary' in problem_text or 'cad' in problem_text or 'stent' in problem_text:
                return "Coronary artery disease"
            if 'stroke' in problem_text or 'cva' in problem_text:
                return "Stroke prevention"
            if 'peripheral' in problem_text or 'pad' in problem_text:
                return "Peripheral arterial disease"

        return None

    def _has_afib(self, problems: List[Dict]) -> bool:
        """Check if patient has atrial fibrillation."""
        for p in problems:
            name = p.get('name', '').lower()
            icd = p.get('icd10_code', '').upper()
            if 'atrial fibrillation' in name or 'afib' in name or icd.startswith('I48'):
                return True
        return False

    def _has_ckd(self, problems: List[Dict]) -> bool:
        """Check if patient has CKD (affects DOAC dosing/hold time)."""
        for p in problems:
            name = p.get('name', '').lower()
            icd = p.get('icd10_code', '').upper()
            if 'chronic kidney' in name or 'ckd' in name or icd.startswith('N18'):
                return True
        return False

    def _calculate_chadsvasc(self, problems: List[Dict]) -> int:
        """Calculate CHA2DS2-VASc score."""
        score = 0
        problem_text = ' '.join(p.get('name', '').lower() for p in problems)

        # CHF (+1)
        if 'heart failure' in problem_text or 'chf' in problem_text:
            score += 1
        # Hypertension (+1)
        if 'hypertension' in problem_text or 'htn' in problem_text:
            score += 1
        # Age 75+ (+2) - would need DOB
        # Age 65-74 (+1) - would need DOB
        # Diabetes (+1)
        if 'diabetes' in problem_text:
            score += 1
        # Stroke/TIA (+2)
        if 'stroke' in problem_text or 'tia' in problem_text or 'cva' in problem_text:
            score += 2
        # Vascular disease (+1)
        if 'peripheral' in problem_text or 'pad' in problem_text or 'mi ' in problem_text or 'myocardial infarction' in problem_text:
            score += 1
        # Female (+1) - would need demographics

        return score

    def _assess_thrombotic_risk(
        self,
        at_med: AntithromboticMedication,
        problems: List[Dict],
        chadsvasc: Optional[int]
    ) -> Tuple[bool, Optional[str]]:
        """Assess thrombotic risk for bridging decision."""
        problem_text = ' '.join(p.get('name', '').lower() for p in problems)

        # High risk scenarios
        if 'mechanical valve' in problem_text:
            return (True, "Mechanical heart valve")
        if 'mitral' in problem_text and 'mechanical' in problem_text:
            return (True, "Mechanical mitral valve")
        if chadsvasc and chadsvasc >= 5:
            return (True, f"CHA2DS2-VASc {chadsvasc}")
        if 'recent dvt' in problem_text or 'recent pe' in problem_text:
            return (True, "Recent VTE")
        if 'recent stroke' in problem_text:
            return (True, "Recent stroke")

        return (False, None)

    def _assess_bleeding_risk(
        self,
        surgery_type: str,
        problems: List[Dict]
    ) -> Tuple[bool, Optional[str]]:
        """Assess procedural bleeding risk."""
        # High bleeding risk surgeries
        high_risk_procedures = ['cardiac', 'intracranial', 'spinal', 'major vascular']

        if any(p in surgery_type.lower() for p in high_risk_procedures):
            return (True, f"High-risk procedure ({surgery_type})")

        # Patient factors
        problem_text = ' '.join(p.get('name', '').lower() for p in problems)
        if 'thrombocytopenia' in problem_text:
            return (True, "Thrombocytopenia")
        if 'coagulopathy' in problem_text:
            return (True, "Coagulopathy")

        return (False, None)


# ==============================================================================
# UNIFIED VASCULAR ASSESSMENT
# ==============================================================================

@dataclass
class VascularAssessment:
    """Complete vascular surgery preoperative assessment."""
    patient_id: str
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    pad: Optional[PADAssessment] = None
    carotid: Optional[CarotidAssessment] = None
    aaa: Optional[AAAAssessment] = None
    bridging: Optional[BridgingPlan] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "assessed_at": self.assessed_at,
            "pad": self.pad.to_dict() if self.pad else None,
            "carotid": self.carotid.to_dict() if self.carotid else None,
            "aaa": self.aaa.to_dict() if self.aaa else None,
            "bridging": self.bridging.to_dict() if self.bridging else None,
        }

    def generate_preop_summary(self) -> str:
        """Generate preoperative summary for surgical planning."""
        lines = [
            "=" * 60,
            "VASCULAR SURGERY PREOPERATIVE ASSESSMENT",
            f"Patient: {self.patient_id}",
            f"Generated: {self.assessed_at}",
            "=" * 60,
        ]

        # PAD Summary
        if self.pad:
            lines.append("\n## PERIPHERAL ARTERIAL DISEASE")
            lines.append(f"Rutherford: {self.pad.rutherford_description()}")
            if self.pad.worst_abi():
                lines.append(f"Worst ABI: {self.pad.worst_abi().value} ({self.pad.worst_abi().interpretation})")
            if self.pad.cli_present():
                lines.append("*** CRITICAL LIMB ISCHEMIA PRESENT ***")
            lines.append(f"Amputation Risk: {self.pad.amputation_risk()}")
            if self.pad.prior_bypass:
                lines.append(f"Prior Bypass: {', '.join(self.pad.prior_bypass)}")

        # Carotid Summary
        if self.carotid:
            lines.append("\n## CAROTID DISEASE")
            side, pct = self.carotid.dominant_stenosis()
            lines.append(f"Stenosis: {pct}% ({side})")
            lines.append(f"Symptom Status: {self.carotid.symptom_status.value}")
            indicated, reason = self.carotid.intervention_indicated()
            if indicated:
                lines.append(f"*** INTERVENTION INDICATED: {reason} ***")

        # AAA Summary
        if self.aaa:
            lines.append("\n## ABDOMINAL AORTIC ANEURYSM")
            if self.aaa.current_diameter():
                lines.append(f"Current Diameter: {self.aaa.current_diameter()} cm")
            growth = self.aaa.growth_rate_cm_per_year()
            if growth:
                lines.append(f"Growth Rate: {growth} cm/year")
            lines.append(f"EVAR Suitability: {self.aaa.evar_suitability().value}")
            indicated, reason = self.aaa.repair_indicated()
            if indicated:
                lines.append(f"*** REPAIR INDICATED: {reason} ***")

        # Bridging Summary
        if self.bridging and self.bridging.recommendations:
            lines.append("\n## ANTITHROMBOTIC MANAGEMENT")
            lines.append(self.bridging._generate_summary())

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class VascularExtractorSuite:
    """Unified extractor suite for all vascular pathology."""

    def __init__(self):
        self.pad_extractor = PADExtractor()
        self.carotid_extractor = CarotidExtractor()
        self.aaa_extractor = AAAExtractor()
        self.bridging_calculator = AntithromboticBridgingCalculator()

    def extract_all(
        self,
        patient_id: str,
        clinical_data: Dict[str, Any],
        surgery_type: str = "vascular",
        surgery_date: Optional[str] = None
    ) -> VascularAssessment:
        """
        Extract complete vascular assessment.

        Args:
            patient_id: Patient identifier
            clinical_data: Dict containing medications, problems, vitals, notes, imaging, etc.
            surgery_type: Type of planned surgery
            surgery_date: Planned surgery date

        Returns:
            VascularAssessment with all extracted data
        """
        assessment = VascularAssessment(patient_id=patient_id)

        # Run all extractors
        assessment.pad = self.pad_extractor.extract(patient_id, clinical_data)
        assessment.carotid = self.carotid_extractor.extract(patient_id, clinical_data)
        assessment.aaa = self.aaa_extractor.extract(patient_id, clinical_data)

        # Calculate bridging plan
        assessment.bridging = self.bridging_calculator.calculate_bridging_plan(
            patient_id=patient_id,
            medications=clinical_data.get('medications', []),
            problems=clinical_data.get('problems', []),
            surgery_type=surgery_type,
            surgery_date=surgery_date
        )

        logger.info(f"[VASCULAR] Complete assessment extracted for patient {patient_id}")
        return assessment


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

# Global extractor instance
_vascular_suite: Optional[VascularExtractorSuite] = None


def get_vascular_extractor() -> VascularExtractorSuite:
    """Get or create the global vascular extractor suite."""
    global _vascular_suite
    if _vascular_suite is None:
        _vascular_suite = VascularExtractorSuite()
    return _vascular_suite


def extract_vascular_assessment(
    patient_id: str,
    clinical_data: Dict[str, Any],
    surgery_type: str = "vascular"
) -> VascularAssessment:
    """
    Convenience function to extract complete vascular assessment.

    Args:
        patient_id: Patient identifier
        clinical_data: Clinical data dictionary
        surgery_type: Type of planned surgery

    Returns:
        VascularAssessment with all extracted data
    """
    suite = get_vascular_extractor()
    return suite.extract_all(patient_id, clinical_data, surgery_type)
