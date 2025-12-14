# AthenaNet Shadow EHR: Surgical Command Center

## Real-Time Clinical Intelligence for Vascular Surgery Decision Support

**Version:** 2.0.0
**Architecture:** 4-Layer Clinical Processing Pipeline
**AI Providers:** Claude (Anthropic), GPT-4 (OpenAI), Gemini (Google)
**Data Standard:** HL7 FHIR R4

---

## Overview

The **Surgical Command Center** is a clinical decision support system that extracts real-time patient data from AthenaHealth EHR through browser-level API interception. It provides vascular surgeons with:

- **Antithrombotic Management Alerts** - Critical perioperative medication tracking
- **Cardiovascular Risk Assessment** - RCRI-like automated risk stratification
- **AI-Powered Surgical Briefings** - Context-aware clinical summaries
- **Real-Time Data Stream** - FHIR-normalized clinical data as physicians navigate

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [4-Layer Architecture](#4-layer-architecture)
3. [AI Integration](#ai-integration)
4. [API Reference](#api-reference)
5. [Configuration](#configuration)
6. [Installation](#installation)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/your-org/athena-shadow-ehr.git
cd athena-shadow-ehr

# 2. Install backend dependencies
cd backend
pip install -r requirements.txt

# 3. Configure API keys (edit .env)
cp .env.example .env
# Add your ANTHROPIC_API_KEY, OPENAI_API_KEY, or use existing GEMINI_API_KEY

# 4. Start backend
python main.py

# 5. Load Chrome extension
# Go to chrome://extensions → Enable Developer Mode → Load unpacked → select extension/

# 6. Start frontend (optional)
cd ../frontend && npm install && npm run dev
```

---

## 4-Layer Architecture

The system processes clinical data through four specialized layers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SURGICAL COMMAND CENTER                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LAYER 1: RAW EVENT STORE                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Captures ALL intercepted API payloads                               │ │
│  │  • Persists to data/raw_events.jsonl                                   │ │
│  │  • Enables replay, audit, and drift detection                          │ │
│  │  • Endpoints: /events/raw                                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  LAYER 2: EVENT INDEXER                                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Classifies events by clinical category                              │ │
│  │  • Categories: medication, problem, vital, lab, allergy, etc.          │ │
│  │  • URL pattern matching + payload key inspection                       │ │
│  │  • Confidence scoring for classification quality                       │ │
│  │  • Endpoints: /index/query, /index/stats, /index/reindex              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  LAYER 3: CLINICAL INTERPRETERS                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  MedicationInterpreter:                                                │ │
│  │    • Extracts from Athena's Events[].Instance.DisplayName              │ │
│  │    • Flags antithrombotics (clopidogrel, warfarin, DOACs, etc.)       │ │
│  │    • Categorizes: anticoagulants vs antiplatelets                     │ │
│  │                                                                        │ │
│  │  ProblemInterpreter:                                                   │ │
│  │    • Extracts ICD-10 and SNOMED codes                                 │ │
│  │    • Flags vascular conditions (I70-I74, I77)                         │ │
│  │    • Identifies CV risk factors (diabetes, CKD, CAD, CHF)             │ │
│  │                                                                        │ │
│  │  Endpoints: /clinical/{patient_id}, /clinical/{patient_id}/medications│ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  LAYER 4: AI SUMMARIZER                                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Template-based surgical briefings (no API needed)                   │ │
│  │  • LLM-enhanced summaries via Claude, GPT-4, or Gemini                │ │
│  │  • RCRI-like cardiovascular risk assessment                           │ │
│  │  • Medication management alerts with hold recommendations             │ │
│  │                                                                        │ │
│  │  Endpoints: /ai/briefing/{patient_id}, /ai/risk/{patient_id}          │ │
│  │             /ai/med-alert/{patient_id}, /ai/context/{patient_id}      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AI Integration

### Supported Providers

| Provider | Model | Best For | Cost |
|----------|-------|----------|------|
| **Claude** | claude-sonnet-4-20250514 | Complex medical reasoning | ~$3/M tokens |
| **GPT-4** | gpt-4-turbo-preview | Backup option | ~$10/M tokens |
| **Gemini** | gemini-pro | Free tier available | Free/Low |
| **Template** | N/A | Fast, reliable (default) | Free |

### Configuration

Add API keys to `.env`:

```ini
# Anthropic Claude (recommended for medical reasoning)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI GPT-4 (backup)
OPENAI_API_KEY=sk-...

# Google Gemini (already configured)
GEMINI_API_KEY=AIzaSy...
GOOGLE_API_KEY=AIzaSy...
```

### Usage

The system defaults to **template-based briefings** (fast, no API calls). To use LLM-enhanced summaries:

```bash
# Template-based (default, no API needed)
curl http://localhost:8000/ai/briefing/12345

# Get context formatted for any LLM
curl "http://localhost:8000/ai/context/12345?format=prompt"
```

---

## API Reference

### Layer 1: Raw Events

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events/raw` | GET | Get raw intercepted events |
| `/events/index` | GET | Get interpreter index entries |

### Layer 2: Event Indexer

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/index/query` | GET | Query indexed events with filters |
| `/index/stats` | GET | Get category statistics |
| `/index/reindex` | POST | Reprocess all raw events |

**Query Parameters:**
- `patient_id` - Filter by patient
- `category` - medication, problem, vital, lab, allergy, compound
- `source_type` - passive_intercept, active_fetch
- `min_confidence` - 0.0 to 1.0

### Layer 3: Clinical Interpreters

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/clinical/{patient_id}` | GET | All interpreted data for patient |
| `/clinical/{patient_id}/medications` | GET | Medications (use `?antithrombotic_only=true`) |
| `/clinical/{patient_id}/problems` | GET | Problems (use `?vascular_only=true`) |
| `/clinical/{patient_id}/summary` | GET | Clinical summary for vascular surgery |
| `/clinical/interpreters` | GET | List registered interpreters |

### Layer 4: AI Summarizer

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai/briefing/{patient_id}` | GET | Surgical briefing with antithrombotic alerts |
| `/ai/med-alert/{patient_id}` | GET | Medication management alerts |
| `/ai/risk/{patient_id}` | GET | RCRI-like cardiovascular risk score |
| `/ai/context/{patient_id}` | GET | Structured context (JSON or prompt format) |

### Layer 5: Artifact & Document Downloads

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/context` | POST | Update session context from Chrome extension |
| `/session/context` | GET | Get current session status |
| `/artifacts` | GET | List stored artifacts (`?patient_id=xxx`) |
| `/artifacts/stats` | GET | Storage statistics |
| `/artifacts/{artifact_id}` | GET | Get artifact metadata |
| `/artifacts/{artifact_id}/download` | GET | Download artifact (base64) |
| `/artifacts/detect-missing` | POST | Detect missing documents from payload |
| `/artifacts/download` | POST | Download single document (HTTP-first) |
| `/artifacts/batch-download` | POST | Download multiple documents |

**Download Strategy:**
1. **HTTP-First** - Uses captured session cookies (fast, no browser)
2. **Selenium Fallback** - Only if HTTP fails and enabled (isolated service)

### WebSocket Endpoints

| Endpoint | Purpose |
|----------|---------|
| `ws://localhost:8000/ws/chrome` | Chrome extension connection |
| `ws://localhost:8000/ws/frontend` | React frontend connection |

**Message Types (Server → Client):**
```json
{"type": "PATIENT_UPDATE", "data": {...}}
{"type": "CLINICAL_UPDATE", "data": {"patient_id": "...", "category": "medication", "records": [...]}}
{"type": "LOG_ENTRY", "data": {...}}
```

---

## Configuration

### Environment Variables (.env)

```ini
# ============================================================================
# AI PROVIDER API KEYS (for Clinical Summarization)
# ============================================================================

# Anthropic Claude (recommended for medical reasoning)
ANTHROPIC_API_KEY=

# OpenAI GPT-4 (backup option)
OPENAI_API_KEY=

# Google Gemini
GEMINI_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here

# ============================================================================
# BACKEND CONFIGURATION
# ============================================================================
BACKEND_PORT=8000
BACKEND_HOST=0.0.0.0

# ============================================================================
# FRONTEND CONFIGURATION
# ============================================================================
VITE_API_URL=http://localhost:8000
VITE_EXTENSION_ID=your_extension_id_here
```

### Clinical Categories (Event Indexer)

The Event Indexer classifies events into these categories:

| Category | Description | Example Patterns |
|----------|-------------|------------------|
| `medication` | Medication lists | `sources=active_medications` |
| `problem` | Diagnoses, conditions | `sources=active_problems` |
| `vital` | Vital signs | `sources=measurements` |
| `lab` | Lab results | `sources=lab` |
| `allergy` | Allergies | `sources=allergies` |
| `compound` | Multi-source requests | `active-fetch/FETCH_ALL` |
| `encounter` | Visit data | `encounter_sections` |
| `demographic` | Patient demographics | `sources=demographics` |

### Antithrombotic Keywords (MedicationInterpreter)

Automatically flagged medications:
- Antiplatelets: aspirin, clopidogrel (Plavix), ticagrelor, prasugrel
- Anticoagulants: warfarin, heparin, enoxaparin, rivaroxaban (Xarelto), apixaban (Eliquis), dabigatran (Pradaxa)

### Vascular ICD-10 Codes (ProblemInterpreter)

| Prefix | Condition |
|--------|-----------|
| I70 | Atherosclerosis |
| I71 | Aortic aneurysm |
| I72 | Other aneurysm |
| I73 | Peripheral vascular diseases |
| I74 | Arterial embolism/thrombosis |
| I77 | Arterial disorders |

---

## Installation

### System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.10+ |
| Node.js | 18+ |
| Chrome | 120+ |
| RAM | 8GB minimum |

### Backend Setup

```bash
cd backend

# Option 1: pip
pip install fastapi uvicorn websockets pydantic python-dotenv
pip install anthropic openai google-generativeai  # For AI providers

# Option 2: conda
conda env create -f environment.yml
conda activate shadow-ehr

# Start server
python main.py
```

### Chrome Extension

1. Navigate to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/` folder
5. Verify badge shows connection status

### Frontend (Optional)

```bash
cd frontend
npm install
npm run dev
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check if port is in use
lsof -i :8000

# Kill existing process
kill -9 $(lsof -t -i:8000)

# Restart
cd backend && python main.py
```

### No Data Appearing

1. Verify Chrome extension is enabled
2. Check extension console for errors (right-click extension icon → Inspect)
3. Verify backend is running: `curl http://localhost:8000/health`
4. Check backend logs for incoming connections

### AI Endpoints Return Errors

1. Verify API keys are set in `.env`
2. Check backend logs: `[AI] Available LLM providers: ['claude', 'gpt4', 'gemini']`
3. Template-based briefings work without any API keys

### High UNKNOWN Event Rate

Check `/index/stats` for category distribution. If many events are UNKNOWN:
- Review endpoint patterns in `backend/event_indexer.py`
- Add new URL patterns to `self.url_patterns` list

---

## Architecture Details

### Data Flow

```
AthenaNet EHR → Chrome Extension → WebSocket → FastAPI Backend
                                                      │
                                   ┌──────────────────┼──────────────────┐
                                   ▼                  ▼                  ▼
                            Raw Event Store    Event Indexer    Clinical Interpreters
                            (Layer 1)          (Layer 2)        (Layer 3)
                                   │                  │                  │
                                   └──────────────────┼──────────────────┘
                                                      ▼
                                              AI Summarizer (Layer 4)
                                                      │
                                                      ▼
                                              Surgical Briefing
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI server, WebSocket handling, API endpoints |
| `backend/event_indexer.py` | Layer 2: Clinical category classification |
| `backend/clinical_interpreters.py` | Layer 3: Medication/problem extraction |
| `backend/ai_summarizer.py` | Layer 4: AI-powered clinical summaries |
| `backend/provenance.py` | Medico-legal traceability for all data |
| `backend/files/session_context.py` | Browser session auth capture |
| `backend/files/http_fetcher.py` | HTTP-first document downloads |
| `backend/files/artifact_store.py` | Document storage with provenance |
| `backend/files/download_manager.py` | Layer 5: HTTP + Selenium fallback orchestration |
| `backend/artifacts/missing_detector.py` | Detect missing documents for download |
| `extension/interceptor.js` | Browser API interception |
| `extension/activeFetcher.js` | Active data fetching with throttling |

---

## Security Notes

- All processing occurs locally (localhost)
- PHI is not transmitted except to configured AI providers
- Patient data is held in RAM only (ephemeral)
- No credentials are stored or captured
- API keys should never be committed to version control
- Session cookies are used for HTTP downloads (short-lived)
- Selenium fallback runs in isolated service (optional)

---

## License

For research and educational purposes. Production clinical use requires regulatory compliance review.

---

## Version History

| Version | Changes |
|---------|---------|
| 2.1.0 | Layer 5: HTTP-first document downloads, provenance tracking, Selenium fallback |
| 2.0.0 | 4-layer architecture, multi-LLM support, vascular surgery focus |
| 1.0.0 | Initial release with Gemini integration |
