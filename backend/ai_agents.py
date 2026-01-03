"""
AI Agent Coordinator - Backend support for Claude/Gemini/Codex delegation

This module provides backend API endpoints for AI agent coordination.
The extension can call these endpoints to delegate tasks to AI agents,
or handle everything client-side.

Usage:
    from ai_agents import router as ai_router
    app.include_router(ai_router)
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger("shadow_ehr.ai_agents")

router = APIRouter(prefix="/ai", tags=["AI Agents"])

# API Keys from environment
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ============================================================
# MODELS
# ============================================================

class AgentRequest(BaseModel):
    agent: str  # "claude", "gemini", "codex"
    task: str
    data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    agent: str
    task: str
    result: Any
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class ClinicalDataRequest(BaseModel):
    patient_id: str
    data_type: str  # "medications", "labs", "problems", "all"
    raw_data: Dict[str, Any]


class SurgicalSummaryRequest(BaseModel):
    patient_id: str
    phase: str  # "preop", "intraop", "postop"
    clinical_data: Dict[str, Any]


class EndpointDiscoveryRequest(BaseModel):
    url: str
    method: str
    response_sample: Optional[str] = None


# ============================================================
# AGENT STATUS
# ============================================================

@router.get("/status")
async def agent_status():
    """Check which AI agents are configured"""
    return {
        "claude": {
            "configured": bool(CLAUDE_API_KEY),
            "role": "CEO",
            "title": "Chief Intelligence Officer",
            "capabilities": ["session_analysis", "traffic_analysis", "strategy_planning", "orchestration"]
        },
        "gemini": {
            "configured": bool(GEMINI_API_KEY),
            "role": "CTO",
            "title": "Senior Data Engineer",
            "capabilities": ["clinical_processing", "fhir_transform", "surgical_summary", "medical_context"]
        },
        "codex": {
            "configured": bool(OPENAI_API_KEY),
            "role": "Engineer",
            "title": "Principal Code Architect",
            "capabilities": ["endpoint_discovery", "fetch_generation", "parser_creation", "api_integration"]
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================
# GENERIC DELEGATION
# ============================================================

@router.post("/delegate", response_model=AgentResponse)
async def delegate_to_agent(request: AgentRequest):
    """Delegate a task to an AI agent"""
    start_time = datetime.utcnow()

    try:
        if request.agent == "claude":
            result = await call_claude(request.task, request.data, request.context)
        elif request.agent == "gemini":
            result = await call_gemini(request.task, request.data, request.context)
        elif request.agent == "codex":
            result = await call_codex(request.task, request.data, request.context)
        else:
            raise HTTPException(400, f"Unknown agent: {request.agent}")

        duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        result.duration_ms = duration
        return result

    except Exception as e:
        logger.error(f"Agent delegation failed: {e}")
        return AgentResponse(
            agent=request.agent,
            task=request.task,
            result=None,
            success=False,
            error=str(e)
        )


# ============================================================
# CLAUDE (CEO) - Strategic Analysis
# ============================================================

async def call_claude(task: str, data: dict, context: dict = None) -> AgentResponse:
    """Claude (CEO) - Strategic analysis and orchestration"""
    if not CLAUDE_API_KEY:
        return AgentResponse(
            agent="claude",
            task=task,
            result=None,
            success=False,
            error="ANTHROPIC_API_KEY not configured"
        )

    # Task-specific prompts
    system_prompt = """You are the CEO/Chief Intelligence Officer of an EHR Bridge system.
Your responsibilities:
- Analyze Athena EHR traffic patterns
- Detect session state and authentication status
- Plan data extraction strategies
- Coordinate with Gemini (clinical processing) and Codex (code generation)
- Ensure HIPAA compliance in all operations

Always respond with structured JSON."""

    task_prompts = {
        "traffic_analysis": f"""Analyze this Athena EHR network request:
{json.dumps(data, indent=2)}

Determine:
1. dataType: What clinical data is this? (medications/labs/problems/documents/vitals/demographics/other)
2. shouldRecord: Is this worth recording? (boolean)
3. endpointPattern: Reusable URL pattern with {{chartId}} placeholder
4. delegateTo: Which agent should process? (gemini/codex/none)
5. hipaaConcerns: Any privacy concerns? (string or null)

Respond with JSON only.""",

        "session_analysis": f"""Analyze this Athena session data:
{json.dumps(data, indent=2)}

Determine:
1. isLoggedIn: Is the user authenticated? (boolean)
2. sessionHealth: Status (good/warning/expired)
3. authTokens: List of auth-related cookies/headers found
4. recommendations: List of suggested actions

Respond with JSON only.""",

        "strategy_planning": f"""Plan a data extraction strategy for this patient:
{json.dumps(data, indent=2)}

Context: {json.dumps(context or {}, indent=2)}

Create an extraction plan:
1. fetchSequence: Ordered list of endpoints to call
2. parallelizable: Which can run in parallel
3. rateLimitMs: Delay between requests
4. criticalData: Must-have data types for vascular surgery
5. fallbackStrategy: What to do if endpoints fail

Respond with JSON only."""
    }

    prompt = task_prompts.get(task, f"Analyze and respond: {json.dumps(data)}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30.0
            )

            if response.status_code == 200:
                result = response.json()
                text = result["content"][0]["text"]

                # Try to parse as JSON
                try:
                    parsed = json.loads(text)
                    return AgentResponse(agent="claude", task=task, result=parsed, success=True)
                except json.JSONDecodeError:
                    return AgentResponse(agent="claude", task=task, result=text, success=True)
            else:
                return AgentResponse(
                    agent="claude",
                    task=task,
                    result=None,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}"
                )

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return AgentResponse(agent="claude", task=task, result=None, success=False, error=str(e))


# ============================================================
# GEMINI (CTO) - Clinical Data Processing
# ============================================================

async def call_gemini(task: str, data: dict, context: dict = None) -> AgentResponse:
    """Gemini (CTO) - Clinical data processing and transformation"""
    if not GEMINI_API_KEY:
        return AgentResponse(
            agent="gemini",
            task=task,
            result=None,
            success=False,
            error="GEMINI_API_KEY not configured"
        )

    task_prompts = {
        "process_clinical": f"""You are a CTO/Senior Data Engineer for a surgical EHR system.

Process this clinical data and extract structured information:
{json.dumps(data, indent=2)}

Focus on vascular surgery relevance:
1. medications: Extract all, flag anticoagulants (warfarin, eliquis, xarelto, plavix, aspirin)
2. labs: Extract with clinical context, prioritize Cr/eGFR, PT/INR, CBC
3. problems: Categorize by relevance to vascular surgery
4. allergies: Flag contrast, latex, heparin, protamine

Return structured JSON.""",

        "surgical_summary": f"""Generate a vascular surgery pre-operative summary:
{json.dumps(data, indent=2)}

Format as:
## ANTICOAGULATION STATUS
- Current medications and last doses
- Hold instructions

## RENAL FUNCTION
- Creatinine, eGFR
- Contrast precautions if needed

## CARDIAC RISK
- Recent stress test/echo
- Ejection fraction
- Clearance status

## VASCULAR HISTORY
- Previous procedures
- Stent/graft locations

## CRITICAL ALLERGIES
- Contrast, latex, heparin reactions""",

        "fhir_transform": f"""Convert this Athena data to FHIR R4 format:
{json.dumps(data, indent=2)}

Return valid FHIR JSON Bundle."""
    }

    prompt = task_prompts.get(task, f"Process this clinical data: {json.dumps(data)}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}
                },
                timeout=60.0
            )

            if response.status_code == 200:
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]

                # Try to parse as JSON
                try:
                    # Handle markdown code blocks
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(text)
                    return AgentResponse(agent="gemini", task=task, result=parsed, success=True)
                except (json.JSONDecodeError, IndexError):
                    return AgentResponse(agent="gemini", task=task, result=text, success=True)
            else:
                return AgentResponse(
                    agent="gemini",
                    task=task,
                    result=None,
                    success=False,
                    error=f"HTTP {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return AgentResponse(agent="gemini", task=task, result=None, success=False, error=str(e))


# ============================================================
# CODEX (Engineer) - Code Generation
# ============================================================

async def call_codex(task: str, data: dict, context: dict = None) -> AgentResponse:
    """Codex (Engineer) - Code generation and endpoint discovery"""
    if not OPENAI_API_KEY:
        return AgentResponse(
            agent="codex",
            task=task,
            result=None,
            success=False,
            error="OPENAI_API_KEY not configured"
        )

    system_prompt = """You are a Principal Engineer specializing in:
- Chrome extension development
- Healthcare API integration (Athena EHR)
- JavaScript/TypeScript
- Data parsing and transformation

Generate clean, production-ready code with error handling."""

    task_prompts = {
        "endpoint_discovery": f"""Analyze this network request and generate endpoint configuration:
{json.dumps(data, indent=2)}

Return JSON:
{{
  "pattern": "/path/{{chartId}}/endpoint",
  "method": "GET",
  "requiredHeaders": ["X-CSRF-Token"],
  "queryParams": ["param1", "param2"],
  "responseSchema": {{...}},
  "dataType": "medications|labs|problems|etc"
}}""",

        "generate_fetcher": f"""Generate a JavaScript fetch function for this endpoint:
{json.dumps(data, indent=2)}

Requirements:
- Use captured session headers
- Include retry logic (3 attempts)
- Parse response JSON
- Handle errors gracefully
- Add JSDoc comments

Return only the code.""",

        "generate_parser": f"""Create a parser function for this Athena response:
{json.dumps(data, indent=2)}

The parser should:
- Extract relevant fields
- Normalize data structure
- Handle missing fields gracefully
- Return typed object

Return JavaScript/TypeScript code."""
    }

    prompt = task_prompts.get(task, f"Generate code for: {json.dumps(data)}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4-turbo",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096
                },
                timeout=60.0
            )

            if response.status_code == 200:
                result = response.json()
                text = result["choices"][0]["message"]["content"]

                # Try to parse as JSON if it looks like JSON
                try:
                    if text.strip().startswith("{"):
                        parsed = json.loads(text)
                        return AgentResponse(agent="codex", task=task, result=parsed, success=True)
                except json.JSONDecodeError:
                    pass

                return AgentResponse(agent="codex", task=task, result=text, success=True)
            else:
                return AgentResponse(
                    agent="codex",
                    task=task,
                    result=None,
                    success=False,
                    error=f"HTTP {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Codex API error: {e}")
        return AgentResponse(agent="codex", task=task, result=None, success=False, error=str(e))


# ============================================================
# CONVENIENCE ENDPOINTS
# ============================================================

@router.post("/process-clinical", response_model=AgentResponse)
async def process_clinical_data(request: ClinicalDataRequest):
    """Process clinical data with Gemini (CTO)"""
    return await call_gemini("process_clinical", {
        "patient_id": request.patient_id,
        "data_type": request.data_type,
        "data": request.raw_data
    })


@router.post("/surgical-summary", response_model=AgentResponse)
async def generate_surgical_summary(request: SurgicalSummaryRequest):
    """Generate surgical summary with Gemini (CTO)"""
    return await call_gemini("surgical_summary", {
        "patient_id": request.patient_id,
        "phase": request.phase,
        "clinical_data": request.clinical_data
    })


@router.post("/discover-endpoint", response_model=AgentResponse)
async def discover_endpoint(request: EndpointDiscoveryRequest):
    """Discover endpoint pattern with Codex (Engineer)"""
    return await call_codex("endpoint_discovery", {
        "url": request.url,
        "method": request.method,
        "response_sample": request.response_sample
    })


@router.post("/analyze-traffic", response_model=AgentResponse)
async def analyze_traffic(data: Dict[str, Any]):
    """Analyze traffic with Claude (CEO)"""
    return await call_claude("traffic_analysis", data)
