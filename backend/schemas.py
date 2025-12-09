"""
Pydantic schemas for data validation.
Defines the data structures for AthenaNet payloads and FHIR resources.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, List
from datetime import datetime
from enum import Enum


class ScraperMode(str, Enum):
    PASSIVE = "PASSIVE"
    ACTIVE = "ACTIVE"


class AthenaPayload(BaseModel):
    """Payload structure received from Chrome extension."""
    endpoint: str
    method: str = "GET"
    payload: Any = None


class VitalComponent(BaseModel):
    """Individual vital sign component."""
    code: str
    display: str
    value: Any
    unit: Optional[str] = None


class FHIRObservation(BaseModel):
    """Simplified FHIR R4 Observation resource."""
    resourceType: str = "Observation"
    id: Optional[str] = None
    status: str = "final"
    code: str = ""
    display: str = ""
    components: List[VitalComponent] = []
    effectiveDateTime: Optional[str] = None


class FHIRCondition(BaseModel):
    """Simplified FHIR R4 Condition resource."""
    resourceType: str = "Condition"
    id: Optional[str] = None
    code: str = ""
    display: str = ""
    clinicalStatus: str = "active"
    onsetDateTime: Optional[str] = None


class FHIRMedication(BaseModel):
    """Simplified FHIR R4 MedicationStatement resource."""
    resourceType: str = "MedicationStatement"
    id: Optional[str] = None
    name: str = ""
    dose: Optional[str] = None
    frequency: Optional[str] = None
    status: str = "active"


class FHIRPatient(BaseModel):
    """Simplified FHIR R4 Patient resource."""
    resourceType: str = "Patient"
    id: Optional[str] = None
    identifier: List[dict] = []
    name: dict = Field(default_factory=lambda: {"full": "", "given": [], "family": ""})
    birthDate: Optional[str] = None
    gender: Optional[str] = None
    telecom: List[dict] = []
    address: List[dict] = []


class Vitals(BaseModel):
    """Vitals structure for frontend."""
    bp: str = "--/--"
    hr: int = 0
    temp: float = 98.6
    spo2: int = 0


class Patient(BaseModel):
    """Full patient structure for frontend consumption."""
    id: str
    mrn: str
    name: str
    dob: str = ""
    gender: str = ""
    lastEncounter: str = ""
    conditions: List[str] = []
    medications: List[str] = []
    vitals: Vitals = Field(default_factory=Vitals)
    notes: str = ""


class LogEntry(BaseModel):
    """Log entry for the frontend live log."""
    id: str
    timestamp: str
    method: str
    endpoint: str
    status: int = 200
    size: str = "0kb"
    payload: Any = None


class WebSocketMessage(BaseModel):
    """Message structure for frontend WebSocket communication."""
    type: str  # LOG_ENTRY, PATIENT_UPDATE, STATUS_UPDATE
    data: Any


class ModeChangeRequest(BaseModel):
    """Request to change scraper mode."""
    action: str = "SET_MODE"
    mode: ScraperMode
