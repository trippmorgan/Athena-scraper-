# AthenaNet Shadow EHR: Autonomous Clinical Intelligence Overlay

## A Dissertation on Parasitic Browser Architecture for Real-Time Clinical Data Liberation

**Version:** 1.0.0
**Architecture Pattern:** Parasitic Sidecar / Man-in-the-Browser (MitB) Overlay
**Intelligence Engine:** Google Gemini 2.5 Flash (Multi-Agent Swarm)
**Data Standard:** HL7 FHIR R4 (Fast Healthcare Interoperability Resources)

---

## Abstract

The **AthenaNet Shadow EHR** represents a novel approach to clinical data interoperability through browser-level API interception. Traditional EHR integration methodologies rely on vendor-provided APIs, HL7 ADT feeds, or direct database connections—each constrained by vendor lock-in, contractual barriers, and latency. This system circumvents these limitations by implementing a **parasitic overlay architecture** that intercepts the native JSON payloads exchanged between the AthenaHealth frontend and its backend services.

The result is a real-time, FHIR-normalized clinical data stream that powers autonomous AI agents capable of documentation generation, risk stratification, and medical coding—functioning as a cognitive augmentation layer for clinical workflows.

---

## Table of Contents

1. [Theoretical Foundations](#1-theoretical-foundations)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Data Flow & Transformation Pipeline](#4-data-flow--transformation-pipeline)
5. [Installation & Deployment](#5-installation--deployment)
6. [Configuration](#6-configuration)
7. [Operational Workflow](#7-operational-workflow)
8. [Security Considerations](#8-security-considerations)
9. [API Reference](#9-api-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Theoretical Foundations

### 1.1 The Interoperability Problem in Healthcare IT

Electronic Health Record (EHR) systems represent one of the most significant barriers to healthcare innovation. Despite mandates like the 21st Century Cures Act and ONC's Information Blocking Rule, EHR vendors maintain de facto data silos through:

- **Proprietary API schemas** that deviate from FHIR/HL7 standards
- **Rate-limited or paywalled API access** requiring per-patient licensing fees
- **Asynchronous batch exports** that preclude real-time clinical decision support

### 1.2 The Browser as an Interception Point

Modern web-based EHRs like AthenaHealth operate as Single Page Applications (SPAs) that communicate with backend services via RESTful JSON APIs. This architecture presents an interception opportunity: **the browser already receives the complete clinical dataset** required to render the physician's view.

By intercepting these API responses at the JavaScript runtime level, we achieve:

1. **Zero-latency data access** (data captured as it renders)
2. **Complete data fidelity** (identical to what the physician sees)
3. **Session-inherited authentication** (no credential management required)

### 1.3 Monkey Patching as an Interception Mechanism

The system employs **prototype chain manipulation** (colloquially "monkey patching") to intercept network requests:

```javascript
// Intercept the native fetch API
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    // Clone and process the response
    return response;
};
```

This technique operates at the JavaScript engine level, making it transparent to the host application while capturing all network traffic.

---

## 2. System Architecture

The system implements a **four-tier pipeline architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TIER 1: INTERCEPTION                           │
│                         Chrome Extension (Manifest V3)                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │ interceptor  │───▶│   injector   │───▶│  background  │                   │
│  │    .js       │    │     .js      │    │     .js      │                   │
│  │ (Page Ctx)   │    │(Content Scr) │    │(Svc Worker)  │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│        │                                        │                            │
│        │ window.postMessage                     │ HTTP POST                  │
│        ▼                                        ▼                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                           TIER 2: NORMALIZATION                              │
│                         Python FastAPI Backend                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         /ingest endpoint                              │   │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐                  │   │
│  │  │  Payload   │───▶│   FHIR     │───▶│  Patient   │                  │   │
│  │  │  Parser    │    │ Converter  │    │   Cache    │                  │   │
│  │  └────────────┘    └────────────┘    └────────────┘                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    │ WebSocket                               │
│                                    ▼                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                            TIER 3: PRESENTATION                              │
│                         React 19 Command Center                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐      │
│  │  Patient   │    │  LiveLog   │    │   Mirror   │    │    AI      │      │
│  │   Card     │    │  Console   │    │   Ledger   │    │  Agents    │      │
│  └────────────┘    └────────────┘    └────────────┘    └────────────┘      │
├─────────────────────────────────────────────────────────────────────────────┤
│                            TIER 4: INTELLIGENCE                              │
│                      Google Gemini 2.5 Flash API                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │   Summarizer   │  │ Risk Predictor │  │ Coding Agent   │                 │
│  │     Agent      │  │     Agent      │  │    (ICD/CPT)   │                 │
│  └────────────────┘  └────────────────┘  └────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Tier 1: Browser Interception Layer

**Components:**
- `interceptor.js` — Executes in page context; patches `window.fetch` and `XMLHttpRequest.prototype`
- `injector.js` — Content script that bridges isolated worlds via `window.postMessage`
- `background.js` — Service worker that maintains HTTP connection to backend with offline queue

**Execution Contexts:**
```
┌─────────────────────────────────────────────────────────┐
│                    Chrome Browser                        │
│  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │  Page Context   │  │    Extension Context         │   │
│  │  (Main World)   │  │  ┌─────────┐  ┌──────────┐  │   │
│  │                 │  │  │Content  │  │ Service  │  │   │
│  │ interceptor.js  │◀─┼──│ Script  │  │ Worker   │  │   │
│  │ (has access to  │  │  │injector │  │background│  │   │
│  │  window.fetch)  │  │  └─────────┘  └──────────┘  │   │
│  └─────────────────┘  └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Tier 2: Normalization Engine

The Python backend performs **ETL (Extract, Transform, Load)** operations:

1. **Extract:** Receive raw AthenaNet JSON via HTTP POST
2. **Transform:** Apply schema mapping to FHIR R4 resources
3. **Load:** Cache patient data and broadcast to connected frontends

**FHIR Resource Mapping:**
| AthenaNet Entity | FHIR R4 Resource |
|------------------|------------------|
| Patient Demographics | `Patient` |
| Vital Signs | `Observation` (category: vital-signs) |
| Problem List | `Condition` |
| Medications | `MedicationStatement` |
| Lab Results | `Observation` (category: laboratory) |
| Allergies | `AllergyIntolerance` |

### 2.3 Tier 3: Presentation Layer

React 19 application providing:
- Real-time patient card with aggregated clinical data
- Live log console showing intercepted API traffic
- Mirror Ledger for audit trail and data provenance
- AI agent orchestration and output display

### 2.4 Tier 4: Intelligence Layer

Multi-agent system using Google Gemini 2.5 Flash:
- **Clinical Summarizer:** Generates SOAP notes from raw clinical data
- **Risk Predictor:** Calculates clinical risk scores with evidence chains
- **Coding Assistant:** Suggests ICD-10 and CPT codes for billing

---

## 3. Technology Stack

### 3.1 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| **React** | 19.x | Component framework with concurrent rendering |
| **TypeScript** | 5.x | Static type checking for clinical data structures |
| **Vite** | 5.x | Build tooling with HMR (Hot Module Replacement) |
| **TailwindCSS** | 3.x | Utility-first CSS framework |
| **Lucide React** | Latest | Icon library |

### 3.2 Backend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.10+ | Runtime with advanced asyncio support |
| **FastAPI** | 0.100+ | Async web framework with automatic OpenAPI docs |
| **Uvicorn** | 0.23+ | ASGI server with WebSocket support |
| **Pydantic** | 2.x | Data validation and serialization |
| **Websockets** | 11.x | Bidirectional communication protocol |

### 3.3 Browser Extension

| Technology | Version | Purpose |
|------------|---------|---------|
| **Chrome Manifest** | V3 | Extension platform specification |
| **Service Worker** | ES2020 | Background processing with fetch API |
| **Content Scripts** | Isolated | DOM access and message bridging |

### 3.4 External Services

| Service | Purpose |
|---------|---------|
| **Google Gemini API** | Large Language Model for clinical AI agents |
| **AthenaHealth** | Target EHR system (requires active session) |

---

## 4. Data Flow & Transformation Pipeline

### 4.1 Interception Flow

```
AthenaNet Server                     Browser                          Backend
      │                                 │                                │
      │  HTTP Response (JSON)           │                                │
      │────────────────────────────────▶│                                │
      │                                 │                                │
      │                          ┌──────┴──────┐                         │
      │                          │interceptor.js│                        │
      │                          │ clone resp   │                        │
      │                          │ parse JSON   │                        │
      │                          └──────┬──────┘                         │
      │                                 │                                │
      │                          window.postMessage                      │
      │                                 │                                │
      │                          ┌──────┴──────┐                         │
      │                          │ injector.js │                         │
      │                          │content script│                        │
      │                          └──────┬──────┘                         │
      │                                 │                                │
      │                     chrome.runtime.sendMessage                   │
      │                                 │                                │
      │                          ┌──────┴──────┐                         │
      │                          │background.js│                         │
      │                          │service worker│                        │
      │                          └──────┬──────┘                         │
      │                                 │                                │
      │                          HTTP POST /ingest                       │
      │                                 │────────────────────────────────▶│
      │                                 │                                │
```

### 4.2 URL Pattern Matching

The interceptor uses pattern matching to filter clinical endpoints:

**Capture Patterns (Clinical Data):**
```javascript
capturePatterns: [
    '/chart/',        // Patient chart data
    '/patient/',      // Patient demographics
    '/encounter/',    // Clinical encounters
    '/clinical/',     // Clinical summaries
    '/medications/',  // Medication lists
    '/allergies/',    // Allergy information
    '/labs/',         // Laboratory results
    '/vitals/',       // Vital signs
    '/problems/',     // Problem lists
    '/documents/',    // Clinical documents
    '/orders/',       // Order entries
    '/results/',      // Test results
    '/notes/',        // Clinical notes
    '/api/'           // General API calls
]
```

**Ignore Patterns (Non-Clinical):**
```javascript
ignorePatterns: [
    '/static/',       // Static assets
    '/assets/',       // Asset bundles
    '/analytics/',    // Tracking pixels
    '/tracking/',     // User tracking
    '/telemetry/',    // Telemetry data
    '.js', '.css',    // Code files
    '.png', '.svg',   // Images
    '.woff', '.ico'   // Fonts/icons
]
```

### 4.3 Raw Event Store & Interpreter Index

The backend now persists **all intercepted payloads** before transformation to support replay, drift detection, and audit trails.

- **Raw events:** appended to `data/raw_events.jsonl` with fields for `timestamp`, `endpoint`, `method`, `status`, `patient_id`, `payload_size`, `payload`, and `source`.
- **Interpreter index:** appended to `data/event_index.jsonl`, linking each interpreted record back to its raw event with `event_id`, `record_type`, and `endpoint`.
- **Debug endpoints:** `/events/raw` and `/events/index` expose the most recent entries for a patient, enabling offline analysis without re-scraping.

### 4.4 FHIR Transformation

Raw AthenaNet payloads are transformed to FHIR R4:

**Example: Vital Signs Transformation**

Input (AthenaNet):
```json
{
    "bloodPressure": "120/80",
    "heartRate": 72,
    "temperature": "98.6",
    "respiratoryRate": 16,
    "oxygenSaturation": "99%"
}
```

Output (FHIR R4 Observation):
```json
{
    "resourceType": "Observation",
    "id": "vitals-abc123",
    "status": "final",
    "category": [{
        "coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "vital-signs"
        }]
    }],
    "component": [
        {
            "code": {"text": "Blood Pressure"},
            "valueString": "120/80"
        },
        {
            "code": {"text": "Heart Rate"},
            "valueQuantity": {"value": 72, "unit": "bpm"}
        }
    ]
}
```

---

## 5. Installation & Deployment

### 5.1 System Requirements

| Component | Minimum Requirement |
|-----------|---------------------|
| **Operating System** | macOS 12+, Windows 10+, Ubuntu 20.04+ |
| **Node.js** | v18.0.0 or higher |
| **Python** | 3.10 or higher |
| **Browser** | Google Chrome 120+ |
| **RAM** | 8 GB minimum (16 GB recommended) |
| **Network** | Localhost ports 3000, 5173, 8000 available |

### 5.2 Installation Steps

#### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/athena-shadow-ehr.git
cd athena-shadow-ehr
```

#### Step 2: Install Frontend Dependencies

```bash
# Using npm
npm install

# Or using yarn
yarn install

# Or using pnpm
pnpm install
```

#### Step 3: Install Backend Dependencies

**Option A: Using Conda (Recommended)**
```bash
# Create isolated environment
conda env create -f environment.yml

# Activate environment
conda activate shadow-ehr
```
uvicorn main:app --reload --port 8000

**Option B: Using pip with venv**
```bash
# Create virtual environment
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn websockets pydantic python-dotenv
pip install fastapi>=0.100.0 uvicorn>=0.23.0 pydantic>=2.0.0 google-genai>=0.2.0 python-multipart>=0.0.6
pip install python-dotenv
```

#### Step 4: Configure Environment Variables

Create a `.env` file in the project root:

```ini
# ============================================
# SHADOW EHR CONFIGURATION
# ============================================

# Intelligence Layer (Required)
GEMINI_API_KEY=your_google_gemini_api_key_here

# Backend Configuration (Optional)
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Frontend Configuration (Optional)
VITE_WS_URL=ws://localhost:8000/ws/frontend
VITE_API_URL=http://localhost:8000
```

**Obtaining a Gemini API Key:**
1. Navigate to https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy the key to your `.env` file

#### Step 5: Start the Backend Server

```bash
cd backend
python main.py
```

Expected output:
```
============================================================
  SHADOW EHR BACKEND STARTING
============================================================
WebSocket Endpoints:
  Chrome Extension: ws://localhost:8000/ws/chrome
  React Frontend:   ws://localhost:8000/ws/frontend

REST Endpoints:
  Health Check:     http://localhost:8000/health
  Ingest:           http://localhost:8000/ingest
  Patients:         http://localhost:8000/patients
============================================================
```

#### Step 6: Start the Frontend Development Server

In a new terminal:
```bash
npm run dev
```

Expected output:
```
  VITE v5.x.x  ready in XXX ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.x.x:5173/
```

#### Step 7: Load the Chrome Extension

1. Open Google Chrome
2. Navigate to `chrome://extensions`
3. Enable **Developer mode** (toggle in top-right)
4. Click **Load unpacked**
5. Select the `extension/` directory from this project
6. Verify the extension shows "AthenaNet Clinical Bridge" with status badge

---

## 6. Configuration

### 6.1 Extension Configuration

The extension behavior is configured in `extension/interceptor.js`:

```javascript
const CONFIG = {
    // Endpoints to capture (clinical data)
    capturePatterns: [
        '/chart/', '/patient/', '/encounter/', '/clinical/',
        '/medications/', '/allergies/', '/labs/', '/vitals/',
        '/problems/', '/documents/', '/orders/', '/results/',
        '/notes/', '/api/'
    ],

    // Endpoints to ignore (UI/static)
    ignorePatterns: [
        '/static/', '/assets/', '/analytics/', '/tracking/',
        '/telemetry/', '.js', '.css', '.png', '.svg', '.woff', '.ico'
    ]
};
```

### 6.2 Backend Configuration

The backend server is configured in `backend/main.py`:

```python
# CORS Origins (allowed frontend URLs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server binding
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
```

### 6.3 AI Agent Configuration

Located in `services/geminiService.ts`:

```typescript
const generationConfig = {
    temperature: 0.2,      // Low temperature for deterministic output
    maxOutputTokens: 2048, // Token limit per response
    topP: 0.8,             // Nucleus sampling
    topK: 40               // Top-k sampling
};
```

---

## 7. Operational Workflow

### 7.1 Session Piggybacking

The system operates by **piggybacking on an authenticated AthenaNet session**:

```
┌────────────────────────────────────────────────────────────────────┐
│                     OPERATIONAL SEQUENCE                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. AUTHENTICATION (Manual)                                         │
│     ┌─────────┐                      ┌─────────────┐               │
│     │Physician│────Login + 2FA──────▶│ AthenaNet   │               │
│     └─────────┘                      └─────────────┘               │
│                                                                     │
│  2. SESSION DETECTION (Automatic)                                   │
│     ┌─────────────────┐              ┌─────────────┐               │
│     │Chrome Extension │◀──Detects───│Session Cookies│              │
│     └─────────────────┘              └─────────────┘               │
│                                                                     │
│  3. DATA INTERCEPTION (Automatic)                                   │
│     ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐      │
│     │Physician │──▶│  Views   │──▶│Interceptor│──▶│ Backend │      │
│     │navigates │   │ Patient  │   │ captures │   │processes│      │
│     └──────────┘   └──────────┘   └──────────┘   └─────────┘      │
│                                                                     │
│  4. INTELLIGENCE (Automatic)                                        │
│     ┌─────────┐   ┌─────────┐   ┌─────────────────┐                │
│     │ Backend │──▶│Frontend │──▶│   AI Agents     │                │
│     │ pushes  │   │displays │   │generate insights│                │
│     └─────────┘   └─────────┘   └─────────────────┘                │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### 7.2 Multi-Monitor Workflow

For optimal clinical use:

| Monitor | Content |
|---------|---------|
| **Primary** | AthenaNet (standard clinical workflow) |
| **Secondary** | Shadow EHR Command Center (http://localhost:5173) |

As the physician navigates patient charts in AthenaNet, the Shadow EHR automatically:
1. Captures clinical data
2. Normalizes to FHIR
3. Displays patient summary
4. Generates AI insights

---

## 8. Security Considerations

### 8.1 Data Handling

| Principle | Implementation |
|-----------|----------------|
| **Local Processing** | All data processing occurs on localhost; no PHI transmitted to external servers except Gemini API |
| **Ephemeral Storage** | Patient data held in RAM only; browser refresh clears all clinical data |
| **No Credential Storage** | System never captures or stores AthenaNet credentials |
| **Session Isolation** | Extension only active on AthenaNet domains |

### 8.2 API Key Security

```bash
# NEVER commit API keys to version control
echo ".env" >> .gitignore

# Verify key is not in git history
git log --all --full-history -- .env
```

### 8.3 HIPAA Considerations

- **Minimum Necessary:** Only captures endpoints matching clinical patterns
- **Audit Trail:** Mirror Ledger provides complete data provenance
- **Access Control:** Requires authenticated AthenaNet session
- **Encryption:** HTTPS for all external API calls

---

## 9. API Reference

### 9.1 HTTP Endpoints

#### POST /ingest
Receives captured API data from Chrome extension.

**Request:**
```json
{
    "url": "https://athenanet.athenahealth.com/api/chart/patient/12345",
    "method": "GET",
    "data": { ... },
    "patientId": "12345",
    "source": "fetch",
    "timestamp": "2025-01-15T10:30:00.000Z",
    "size": 4096
}
```

**Response:**
```json
{
    "status": "ok",
    "processed": true,
    "timestamp": "2025-01-15T10:30:00.123Z",
    "patientId": "12345"
}
```

#### GET /health
Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2025-01-15T10:30:00.000Z"
}
```

#### GET /patients
List all cached patients.

**Response:**
```json
{
    "patients": [...],
    "count": 3
}
```

#### GET /stats
Backend statistics.

**Response:**
```json
{
    "payloads_received": 150,
    "payloads_processed": 148,
    "errors": 2,
    "patients_cached": 5,
    "chrome_connections": 1,
    "frontend_connections": 1
}
```

### 9.2 WebSocket Endpoints

#### ws://localhost:8000/ws/frontend
Bidirectional connection for React frontend.

**Server → Client Messages:**
```json
{"type": "PATIENT_UPDATE", "data": {...}}
{"type": "LOG_ENTRY", "data": {...}}
{"type": "STATUS_UPDATE", "data": "CONNECTED"}
```

**Client → Server Messages:**
```json
{"action": "SET_MODE", "mode": "PASSIVE"}
{"action": "SET_MODE", "mode": "ACTIVE"}
```

---

## 10. Troubleshooting

### 10.1 Extension Not Capturing Data

**Symptom:** No log entries appearing in Command Center

**Solutions:**
1. Verify extension is enabled at `chrome://extensions`
2. Check extension badge shows "ON" (green)
3. Open DevTools on AthenaNet tab → Console → Look for `[AthenaNet Bridge]` logs
4. Verify backend is running (`curl http://localhost:8000/health`)

### 10.2 Backend Connection Failed

**Symptom:** Extension badge shows "ERR" (red)

**Solutions:**
```bash
# Check if port 8000 is in use
lsof -i :8000

# Check backend logs
tail -f backend/shadow_ehr.log

# Restart backend
cd backend && python main.py
```

### 10.3 Frontend Not Receiving Updates

**Symptom:** Patient card not updating

**Solutions:**
1. Check browser console for WebSocket errors
2. Verify WebSocket connection: `ws://localhost:8000/ws/frontend`
3. Check backend logs for broadcast messages

### 10.4 AI Agents Not Running

**Symptom:** AI panels show "Error" or remain empty

**Solutions:**
1. Verify `GEMINI_API_KEY` is set in `.env`
2. Check API key validity at https://aistudio.google.com
3. Check browser console for API errors

---

## License

This software is provided for research and educational purposes. Use in production clinical environments requires appropriate regulatory compliance review.

---

## Citation

If you use this architecture in academic work:

```bibtex
@software{athena_shadow_ehr,
    title = {AthenaNet Shadow EHR: Parasitic Browser Architecture for Clinical Data Liberation},
    year = {2025},
    publisher = {GitHub},
    url = {https://github.com/your-org/athena-shadow-ehr}
}
```
