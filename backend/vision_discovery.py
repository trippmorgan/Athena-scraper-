"""
MODULE: Vision-Assisted Endpoint Discovery & Network Topology Analysis
VERSION: 2.1.1 (Bug fix applied)
"""

# Load environment variables before anything else
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import os
import json
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

logger = logging.getLogger("shadow-ehr.discovery")

MODEL_ID = "gemini-2.0-flash"

CLINICAL_LEXICON = {
    'patient': 'demographics',
    'chart': 'demographics', 
    'medication': 'medications', 
    'med': 'medications',
    'prescription': 'medications',
    'allerg': 'allergies', 
    'vital': 'vitals',
    'lab': 'labs', 
    'result': 'labs',
    'problem': 'problems', 
    'condition': 'problems',
    'diagnos': 'problems', 
    'note': 'notes',
    'doc': 'notes', 
    'encounter': 'encounters',
    'order': 'orders'
}

NOISE_PATTERNS = {
    'static', 'asset', 'analytics', 'tracking', 'telemetry',
    '.js', '.css', '.png', '.svg', '.woff', '.ico',
    'datadog', 'sentry', 'google-analytics', 'hotjar', 'newrelic'
}

# SDK Init
try:
    from google import genai
    from google.genai import types
    
    _API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    
    if _API_KEY:
        client = genai.Client(api_key=_API_KEY)
        logger.info(f"GenAI Client initialized. Model: {MODEL_ID}")
    else:
        client = None
        logger.warning("GenAI Client not initialized: Missing API key. Heuristic-only mode.")

except ImportError as e:
    client = None
    logger.critical(f"Missing google-genai package: {e}")


# DTOs
class DiscoveredEndpoint(BaseModel):
    pattern: str = Field(..., description="Normalized URL pattern with {id} placeholders")
    confidence: str = Field("medium", pattern="^(high|medium|low)$")
    description: str = Field("")
    category: str = Field("unknown")
    dataType: Optional[str] = Field(None)

class DiscoveryResponse(BaseModel):
    success: bool
    endpoints: List[DiscoveredEndpoint]
    recommended_config: List[str] = Field(default_factory=list)
    reasoning: str = Field("")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class EndpointSample(BaseModel):
    path: str
    count: int
    methods: List[str]
    avgSize: int

class TrafficReport(BaseModel):
    duration: float
    totalRequests: int
    uniqueEndpoints: int
    endpoints: List[EndpointSample]


# Prompts
VISION_PROMPT = """
ROLE: Senior Backend Engineer & Protocol Analyst.
CONTEXT: Reverse-engineering AthenaNet EHR internal API topology.
INPUT: Chrome DevTools Network Tab Screenshot.

OBJECTIVE: Identify clinical data endpoints from visible network requests.

ALGORITHM:
1. Filter: Isolate XHR/Fetch requests returning JSON. Ignore static assets.
2. Pattern Recognition: Normalize URLs (e.g., /10293/ -> /{id}/).
3. Classification: Tag endpoints carrying PHI (Demographics, Meds, Labs, Notes).

OUTPUT: Pure JSON only. No markdown. Schema:
{
  "endpoints": [{"pattern": "/api/chart/{id}/medications", "confidence": "high", "description": "Active medication list", "category": "Clinical", "dataType": "medications"}],
  "recommended_config": ["/chart/", "/medications/"],
  "reasoning": "Brief analysis"
}
"""

TRAFFIC_PROMPT_TEMPLATE = """
ROLE: Clinical Data Integration Architect.
TASK: Analyze captured network telemetry for clinical endpoints.

INPUT DATA:
{endpoint_data}

RULES:
1. High frequency + small size = status/heartbeat (ignore)
2. Medium frequency + variable size = clinical data (capture)
3. Keywords: chart, patient, clinical, encounter = strong indicators

OUTPUT: Pure JSON matching DiscoveryResponse schema.
"""


# Service Layer
class DiscoveryService:

    @staticmethod
    def _extract_json_from_response(text: str) -> str:
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        return match.group(1) if match else text

    @staticmethod
    def heuristic_analysis(report: TrafficReport) -> DiscoveryResponse:
        logger.info(f"Heuristic analysis on {len(report.endpoints)} endpoints")
        
        discovered = []
        capture_patterns = set()
        
        for ep in report.endpoints:
            path_lower = ep.path.lower()
            
            # BUG FIX: Corrected syntax
            if any(noise in path_lower for noise in NOISE_PATTERNS):
                continue
            
            for keyword, data_type in CLINICAL_LEXICON.items():
                if keyword in path_lower:
                    normalized_path = re.sub(r'/\d+(?=/|$)', '/{id}', ep.path)
                    
                    discovered.append(DiscoveredEndpoint(
                        pattern=normalized_path,
                        confidence="medium",
                        description=f"Heuristic match: {data_type} via '{keyword}'",
                        category="Clinical",
                        dataType=data_type
                    ))
                    capture_patterns.add(f"/{keyword}/")
                    break

        return DiscoveryResponse(
            success=True,
            endpoints=discovered[:50],
            recommended_config=list(capture_patterns)[:20],
            reasoning="Deterministic lexical analysis (LLM unavailable or bypassed)."
        )

    @staticmethod
    async def analyze_vision(image_bytes: bytes, mime_type: str) -> DiscoveryResponse:
        if not client:
            return DiscoveryResponse(
                success=False, 
                endpoints=[], 
                recommended_config=[], 
                reasoning="GenAI Client not initialized. Set GEMINI_API_KEY."
            )

        try:
            payload = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                VISION_PROMPT
            ]

            response = client.models.generate_content(
                model=MODEL_ID,
                contents=payload,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            json_str = DiscoveryService._extract_json_from_response(response.text)
            data = json.loads(json_str)
            return DiscoveryResponse(**data, success=True)

        except Exception as e:
            logger.error(f"Vision inference failed: {e}", exc_info=True)
            return DiscoveryResponse(
                success=False, 
                endpoints=[], 
                recommended_config=[], 
                reasoning=f"Inference error: {str(e)}"
            )

    @staticmethod
    async def analyze_traffic_log(report: TrafficReport) -> DiscoveryResponse:
        if not client:
            return DiscoveryService.heuristic_analysis(report)

        try:
            summary_data = [
                {"path": ep.path, "frequency": ep.count, "methods": ep.methods, "size_bytes": ep.avgSize}
                for ep in report.endpoints[:60]
            ]

            prompt = TRAFFIC_PROMPT_TEMPLATE.format(endpoint_data=json.dumps(summary_data, indent=2))

            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            json_str = DiscoveryService._extract_json_from_response(response.text)
            data = json.loads(json_str)
            return DiscoveryResponse(**data, success=True)

        except Exception as e:
            logger.error(f"Traffic inference failed: {e}", exc_info=True)
            return DiscoveryService.heuristic_analysis(report)


# Router
router = APIRouter(prefix="/discovery", tags=["Endpoint Discovery"])

@router.post("/analyze-screenshot", response_model=DiscoveryResponse)
async def analyze_screenshot_endpoint(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Invalid MIME type. Expected image/*.")
    
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Max 10MB.")

    return await DiscoveryService.analyze_vision(contents, file.content_type)

@router.post("/analyze-traffic", response_model=DiscoveryResponse)
async def analyze_traffic_endpoint(report: TrafficReport):
    return await DiscoveryService.analyze_traffic_log(report)

@router.post("/generate-config")
async def generate_config_endpoint(analysis: DiscoveryResponse) -> Dict[str, Any]:
    patterns = sorted(list(set(analysis.recommended_config)))
    
    js_payload = f"""/**
 * AUTO-GENERATED CONFIGURATION
 * Timestamp: {datetime.now().isoformat()}
 * Reasoning: {analysis.reasoning.replace(chr(10), ' ')}
 */

const CONFIG = {{
    capturePatterns: {json.dumps(patterns, indent=4)},
    
    ignorePatterns: [
        '/static/', '/assets/', '/analytics/', '/tracking/', 
        '.js', '.css', '.png', '.svg', '.woff', '.ico',
        'datadog', 'sentry'
    ]
}};

/**
 * DISCOVERED ENDPOINTS:
{chr(10).join(f" * - {ep.pattern} [{ep.dataType}]" for ep in analysis.endpoints)}
 */
"""
    return {
        "config": {"capturePatterns": patterns},
        "javascript": js_payload,
        "meta": {"generated_at": datetime.now().isoformat()}
    }

@router.get("/status")
async def get_status():
    return {
        "service": "Vision Discovery",
        "llm_provider": "Google GenAI",
        "model_id": MODEL_ID,
        "status": "online" if client else "degraded (heuristic_only)",
        "sdk_version": "v1 (google-genai)"
    }