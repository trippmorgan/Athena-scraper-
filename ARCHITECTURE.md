# Shadow EHR Bridge - System Architecture

## TABLE OF CONTENTS
1. [Mission Statement](#mission-statement)
2. [The Big Picture](#the-big-picture)
3. [Data Sources & Integration](#data-sources--integration)
4. [Critical Data Flow](#critical-data-flow)
5. [Component Deep Dive](#component-deep-dive)
6. [Clinical Use Cases](#clinical-use-cases)
7. [Enhancement Layer (AI Team)](#enhancement-layer-ai-team)
8. [Development Rules](#development-rules)
9. [Troubleshooting](#troubleshooting)
10. [Architectural Decisions Log](#architectural-decisions-log)

---

## MISSION STATEMENT

> **Shadow EHR Bridge unifies clinical data from disparate sources into a coherent,
> surgeon-centric workflow for vascular surgery planning, execution, and quality reporting.**

This is NOT just a data scraper. This is a **clinical decision support system** that:

1. **Captures** patient data from Athena EHR in real-time
2. **Integrates** with external systems (Ultralinq, imaging systems)
3. **Synthesizes** information into surgical narratives
4. **Supports** the entire surgical workflow:
   - Pre-operative planning & risk assessment
   - Intra-operative decision support
   - Post-operative note generation
   - Quality assurance & VQI reporting
5. **Exports** to Plaud/Vascular AI for transcription and analysis

---

## THE BIG PICTURE

```
                                    SHADOW EHR BRIDGE
                                    =================

    DATA SOURCES                         PROCESSING                      OUTPUTS
    ============                         ==========                      =======

    +-------------+                  +------------------+           +------------------+
    | Athena EHR  |----------------->|                  |           | Pre-Op Narrative |
    | - Demographics                 |                  |---------->| (Risk Assessment)|
    | - Medications                  |                  |           +------------------+
    | - Problems                     |   Shadow EHR     |
    | - Labs                         |                  |           +------------------+
    | - Vitals                       |   Backend        |---------->| Surgical Support |
    | - Documents                    |                  |           | (Intra-Op Data)  |
    +-------------+                  |   (Python/       |           +------------------+
                                     |    FastAPI)      |
    +-------------+                  |                  |           +------------------+
    | Ultralinq   |----------------->|                  |---------->| Op Note Draft    |
    | - Echo data                    |                  |           | (Post-Op)        |
    | - Vascular labs                +------------------+           +------------------+
    +-------------+                           |
                                              |                     +------------------+
    +-------------+                           |                     | Quality/VQI      |
    | Imaging     |---------------------------+                     | (Registry Data)  |
    | - CTA/MRA                                                     +------------------+
    | - Duplex                                                              |
    +-------------+                                                         v
                                                                    +------------------+
                                                                    | Plaud/Vascular AI|
                                                                    | Uploader         |
                                                                    +------------------+
```

### Why This Matters

**The Problem:**
Vascular surgeons spend 40%+ of their time on documentation. Clinical data lives in
silos (EHR, imaging systems, labs). Pre-op planning requires manually synthesizing
data from multiple sources.

**The Solution:**
Shadow EHR Bridge automatically captures and synthesizes clinical data, generating
surgeon-ready narratives that support decision-making from consultation through
quality reporting.

---

## DATA SOURCES & INTEGRATION

### Primary Source: Athena EHR (This System)

The Chrome extension intercepts Athena API responses to capture:

| Data Type | Athena Endpoint Pattern | Clinical Use |
|-----------|------------------------|--------------|
| **Demographics** | `sources=demographics` | Patient identification |
| **Active Medications** | `sources=active_medications` | Anticoagulation management |
| **Active Problems** | `sources=active_problems` | Surgical risk factors |
| **Allergies** | `sources=allergies` | Contrast/latex/antibiotic alerts |
| **Vitals** | `sources=measurements` | Hemodynamic status |
| **Documents** | `/ax/data?sources=external_document_links` | Imaging, consults |
| **Historical Problems** | `sources=historical_problems` | Comorbidity context |

### Secondary Sources (Future Integration)

| Source | Data Type | Integration Method |
|--------|-----------|-------------------|
| **Ultralinq** | Echo, vascular lab data | API integration (planned) |
| **PACS/Imaging** | CTA, MRA, duplex reports | Document parsing |
| **Lab Systems** | Coagulation, renal function | HL7/FHIR feeds |

### Output Destinations

| Destination | Purpose | Integration |
|-------------|---------|-------------|
| **Shadow EHR WebUI** | Real-time display | WebSocket |
| **Plaud/Vascular AI** | Transcription, analysis | Export API |
| **VQI Registry** | Quality reporting | Structured export |

---

## CRITICAL DATA FLOW

### The Golden Path (MUST NEVER BREAK)

```
    ATHENA BROWSER TAB                     CHROME EXTENSION                    BACKEND + FRONTEND
    ==================                     ================                    ==================

    [Athena Web App]
          |
          | (Athena makes API calls internally)
          v
    +------------------+
    | interceptor.js   |  <-- Runs IN the Athena page context
    | - Hooks fetch()  |      Captures RESPONSE data from Athena's own API calls
    | - Hooks XHR      |      Does NOT make new requests - only observes
    +------------------+
          |
          | window.postMessage({ type: 'ATHENA_API_INTERCEPT', payload })
          v
    +------------------+
    | injector.js      |  <-- Content script (extension context)
    | - Listens for    |      Bridges page context to extension runtime
    |   postMessage    |
    +------------------+
          |
          | chrome.runtime.sendMessage({ type: 'API_CAPTURE', payload })
          v
    +------------------+
    | background.js    |  <-- Service worker (extension background)
    | - HTTP POST      |      Relays ALL captured data to backend
    |   to /ingest     |      Health checks every 10 seconds
    +------------------+
          |
          | HTTP POST http://localhost:8000/ingest
          v
    +------------------+     +-------------------+
    | main.py          |---->| fhir_converter.py |
    | - FastAPI server |     | - FHIR R4 format  |
    | - Patient cache  |     +-------------------+
    | - WebSocket hub  |
    +------------------+
          |
          | WebSocket PATIENT_UPDATE / LOG_ENTRY
          v
    +------------------+
    | React Frontend   |  <-- Shadow EHR WebUI
    | - SurgicalDash   |      Displays synthesized patient data
    | - NarrativeCard  |      Real-time updates via WebSocket
    +------------------+
```

### Message Types & Payloads

```typescript
// interceptor.js -> injector.js (window.postMessage)
{
  type: 'ATHENA_API_INTERCEPT',
  payload: {
    source: 'fetch' | 'xhr',
    method: 'GET' | 'POST',
    url: string,              // Athena API endpoint
    status: number,           // HTTP status code
    timestamp: string,        // ISO timestamp
    patientId: string | null, // Extracted from URL
    data: object,             // Response JSON
    size: number              // Payload size in bytes
  }
}

// injector.js -> background.js (chrome.runtime.sendMessage)
{
  type: 'API_CAPTURE',
  payload: { /* same as above */ }
}

// background.js -> main.py (HTTP POST /ingest)
{
  url: string,
  method: string,
  data: object,
  source: string,
  timestamp: string,
  patientId: string | null,
  size: number
}

// main.py -> frontend (WebSocket)
{
  type: 'PATIENT_UPDATE',
  data: {
    id: string,
    mrn: string,
    name: string,
    medications: string[],
    conditions: string[],
    vitals: { bp, hr, temp, spo2 },
    // ... clinical data
  }
}
```

### Data Transformation Pipeline

```
Raw Athena Response
       |
       v
+------------------+
| detect_record_   |  Classify: MEDICATION, PROBLEM, VITAL, DEMOGRAPHICS, etc.
| type()           |
+------------------+
       |
       v
+------------------+
| convert_to_fhir()|  Transform to FHIR R4 resources
+------------------+
       |
       v
+------------------+
| update_patient_  |  Merge into patient cache (additive, not replace)
| cache()          |
+------------------+
       |
       v
+------------------+
| broadcast_to_    |  Push to all connected frontends
| frontend()       |
+------------------+
       |
       v
+------------------+
| index_event()    |  Store in event index for retrieval
+------------------+
```

---

## COMPONENT DEEP DIVE

### Extension Components

#### interceptor.js - The Observer
```
PURPOSE: Capture Athena API responses WITHOUT interfering with the application

MECHANISM:
1. Monkey-patches window.fetch and XMLHttpRequest.prototype
2. Lets original request execute normally
3. Clones response for inspection
4. Extracts patient context from URL patterns
5. Posts captured data to content script

CRITICAL: This runs in Athena's page context. Any errors here break Athena itself.
         Code must be defensive and fail silently.

CAPTURE PATTERNS:
- /chart/, /patient/, /encounter/ - Core clinical
- /ax/data?sources= - Athena's data aggregation endpoint
- /medications/, /allergies/, /labs/ - Specific clinical data

IGNORE PATTERNS:
- /static/, /assets/ - UI resources
- .js, .css, .png - Static files
- Analytics/telemetry domains
```

#### injector.js - The Bridge
```
PURPOSE: Bridge page context (interceptor) to extension runtime (background)

WHY NEEDED: Chrome extensions have security boundaries.
            Page scripts cannot directly talk to extension background.
            Content scripts can talk to both, so they act as a bridge.

FLOW:
1. Injects interceptor.js into page context
2. Listens for window.postMessage from interceptor
3. Forwards via chrome.runtime.sendMessage to background
4. Also handles active fetch commands (reverse direction)
```

#### background.js - The Relay
```
PURPOSE: Reliable data transmission to backend, connection management

RESPONSIBILITIES:
- HTTP POST to /ingest for each captured payload
- Health check pings every 10 seconds
- Connection status tracking (connected/disconnected/error)
- Queue management for offline buffering
- Badge updates to show extension status

CRITICAL: Data relay is NON-BLOCKING and ALWAYS FIRST
          AI processing (if any) happens AFTER successful relay
```

### Backend Components

#### main.py - The Hub
```
PURPOSE: Central processing and distribution of clinical data

KEY FUNCTIONS:
- ingest_payload(): Entry point for all captured data
- process_athena_payload(): Orchestrates processing pipeline
- broadcast_to_frontend(): WebSocket distribution
- Patient cache management

WEBSOCKET ENDPOINTS:
- /ws/frontend: React WebUI connects here
- Broadcasts: PATIENT_UPDATE, LOG_ENTRY, STATUS_UPDATE, PING
```

#### fhir_converter.py - The Translator
```
PURPOSE: Transform raw Athena data to FHIR R4 format

WHY FHIR:
- Industry standard for healthcare data interchange
- Structured, validated clinical data models
- Enables interoperability with other systems

KEY FUNCTIONS:
- detect_record_type(): Classify incoming data
- convert_to_fhir(): Transform to FHIR resources
- extract_medications(), extract_conditions(), etc.
```

#### vascular_parser.py - The Synthesizer
```
PURPOSE: Build surgeon-centric profiles from FHIR data

OUTPUT: VascularProfile with:
- Antithrombotics (categorized by type, with hold periods)
- Critical allergies (surgical implications)
- Vascular history (prior procedures)
- Risk flags (bleeding, contrast, cardiac)
```

#### narrative_engine.py - The Narrator
```
PURPOSE: Generate human-readable surgical narratives

FLOW:
1. Gather patient data from cache
2. Build vascular profile
3. Construct LLM prompt with clinical context
4. Generate narrative via Gemini
5. Return structured response with sources
```

### Frontend Components

#### App.tsx - The Controller
```
PURPOSE: Application state management, WebSocket integration

RESPONSIBILITIES:
- WebSocket connection to backend
- Patient state management
- Distributes data to child components
```

#### SurgicalDashboard.tsx - The Display
```
PURPOSE: Surgeon-facing clinical dashboard

FEATURES:
- Phase-based view (Pre-Op, Intra-Op, Post-Op, Notes, Billing)
- Auto-populates from WebSocket patient updates
- Fetches detailed vascular profile
- Displays surgical checklists and alerts
```

---

## CLINICAL USE CASES

### Pre-Operative Planning

**Goal:** Generate a comprehensive pre-op assessment narrative

**Data Required:**
| Category | Data Points | Clinical Decision |
|----------|-------------|------------------|
| Anticoagulation | Warfarin, DOACs, antiplatelets | Hold timing, bridging needs |
| Renal Function | Creatinine, eGFR | Contrast protocol, drug dosing |
| Cardiac Status | EF, stress test, clearance | Operative risk |
| Allergies | Contrast, latex, antibiotics | Prophylaxis, preparation |
| Vascular History | Prior surgeries, stents | Approach planning |

**Workflow:**
1. Extension captures data as user navigates Athena chart
2. Backend builds vascular profile incrementally
3. Narrative engine generates pre-op summary
4. Surgeon reviews and refines for clinic note

### Intra-Operative Support

**Goal:** Real-time access to critical patient information

**Key Features:**
- Quick reference for allergies and medications
- Access to imaging (CTA, duplex) for anatomy review
- Problem list for comorbidity awareness

### Post-Operative Documentation

**Goal:** Accelerate operative note completion

**Workflow:**
1. Capture intra-op data (timing, findings)
2. Integrate with Plaud for voice transcription
3. Generate structured operative note draft
4. Surgeon edits and finalizes

### Quality & Registry Reporting (VQI)

**Goal:** Streamlined data submission to Vascular Quality Initiative

**Data Mapping:**
- Procedure details -> VQI procedure codes
- Complications -> VQI outcome fields
- Patient demographics -> Registry format

---

## ENHANCEMENT LAYER (AI TEAM)

> **IMPORTANT:** The AI Team AUGMENTS the core data flow. It does NOT replace it.
> The system MUST work even if all AI features are disabled or fail.

### Architecture

```
CORE DATA FLOW (always works)
         |
         +---> [AI Enhancement Layer] (optional, graceful degradation)
                    |
                    +-- narrative_engine.py (Gemini) - Generates surgical narratives
                    +-- clinical_interpreters.py - Extracts structured data
                    +-- vascular_parser.py - Builds surgeon-specific profiles

FUTURE (stashed in git):
                    +-- Claude CEO: Session analysis, strategic decisions
                    +-- Gemini CTO: Clinical data processing
                    +-- Codex Principal: Endpoint discovery
```

### Current AI Integration (Active)

| Component | Model | Purpose |
|-----------|-------|---------|
| narrative_engine.py | Gemini | Generates pre-op narratives from clinical data |
| vascular_parser.py | Rule-based | Categorizes medications, flags risks |

### Future AI Integration (Stashed)

The AI Team code is preserved in `git stash@{0}` and can be restored incrementally:
- Claude CEO for session management
- Multi-agent orchestration
- Real-time clinical decision support

---

## DEVELOPMENT RULES

### NEVER DO:
1. Block the core data flow waiting for AI responses
2. Remove the HTTP /ingest fallback
3. Filter out clinical data types from interceptor
4. Break the message chain: interceptor -> injector -> background -> backend
5. Make backend startup depend on AI API keys
6. Commit API keys to the repository

### ALWAYS DO:
1. Relay data to backend FIRST, enhance SECOND
2. Handle AI failures gracefully (catch, log, continue)
3. Preserve the surgical use case focus
4. Test with AI keys missing
5. Log data flow issues at ERROR level
6. Update this document when architecture changes

### Testing Checklist

Before any commit:
- [ ] Extension loads without errors
- [ ] Badge shows ON when backend connected
- [ ] Patient chart navigation triggers captures
- [ ] Data appears in WebUI
- [ ] Core flow works WITHOUT AI keys

---

## TROUBLESHOOTING

### No Data Flowing

1. **Check extension badge** - Should show "ON" when backend running
2. **Check browser console** - Look for `[AthenaNet Bridge]` or `[Shadow EHR]` logs
3. **Check backend terminal** - Look for "INCOMING ATHENA PAYLOAD" logs
4. **Reload extension** - chrome://extensions -> refresh icon
5. **Restart backend** - Kill port 8000, restart main.py

### CORS Errors

Backend CORS is configured for ports 3000-3003 and 5173. If frontend runs on
different port, update `allow_origins` in main.py.

### WebSocket Disconnects

- Frontend WebSocket auto-reconnects with exponential backoff
- Check backend logs for connection/disconnection events
- Verify no other process is using port 8000

### Active Fetch Failing (HTTP 500)

The active fetch feature requires session headers (CSRF tokens) that are
captured from passive intercepts. If active fetch returns 500 errors:
1. Navigate manually in Athena first (passive capture)
2. Then try active fetch
3. Session headers should be captured from passive traffic

---

## ARCHITECTURAL DECISIONS LOG

| Date | Decision | Reason |
|------|----------|--------|
| 2025-01 | Separated AI Team from core relay | AI complexity was breaking data flow |
| 2025-01 | WebSocket primary, HTTP fallback | Reliability over features |
| 2025-01 | Selective capture patterns | Balance between comprehensive data and noise |
| 2025-01 | AI processing is async/non-blocking | Core must work regardless of AI status |
| 2026-01 | CORS expanded to ports 3000-3003 | Frontend port conflicts during development |
| 2026-01 | Added currentPatient prop to SurgicalDashboard | WebSocket data flow to component |
| 2026-01 | Git stash for AI team code | Preserve work while stabilizing core flow |

---

## APPENDIX: FILE REFERENCE

```
/
├── extension/
│   ├── manifest.json         # Chrome MV3 manifest
│   ├── background.js         # Service worker - data relay
│   ├── injector.js           # Content script - bridge
│   ├── interceptor.js        # Page context - capture
│   ├── activeFetcher.js      # Active data fetch (requires session headers)
│   ├── popup.html/js         # Extension UI
│   └── orchestrator.js       # AI team coordination (optional)
│
├── backend/
│   ├── main.py               # FastAPI server, WebSocket hub
│   ├── fhir_converter.py     # FHIR R4 transformation
│   ├── vascular_parser.py    # Surgeon-centric profile builder
│   ├── narrative_engine.py   # LLM narrative generation
│   └── clinical_interpreters.py  # Data extraction
│
├── components/
│   ├── SurgicalDashboard.tsx # Main clinical dashboard
│   ├── NarrativeCard.tsx     # AI narrative display
│   └── RawDataViewer.tsx     # Debug data inspector
│
├── services/
│   ├── websocketService.ts   # Frontend WebSocket client
│   └── apiService.ts         # REST API client
│
└── ARCHITECTURE.md           # This document
```

---

*Last Updated: 2026-01-02*
*Maintainer: Vascular Surgery Informatics Team*
