# Shadow EHR Bridge: Vascular Surgery Command Center

## Mission

> **Unify clinical data from disparate sources into a coherent, surgeon-centric workflow
> for vascular surgery planning, execution, and quality reporting.**

This system solves a fundamental problem: **vascular surgeons spend 40%+ of their time on documentation** while clinical data lives in silos across EHR systems, imaging platforms, and lab systems. Shadow EHR Bridge captures, synthesizes, and presents this data in a surgical workflow context.

---

## The Complete Data Flow

```
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                           VASCULAR SURGERY DATA ECOSYSTEM                        │
    └─────────────────────────────────────────────────────────────────────────────────┘

    DATA SOURCES                    SHADOW EHR                    CLINICAL OUTPUTS
    ============                    ==========                    ================

    ┌─────────────┐                ┌─────────────┐               ┌──────────────────┐
    │  Athena EHR │───────────────>│             │───────────────│  PRE-OP PLANNING │
    │  (Primary)  │                │   Shadow    │               │  - Risk assess   │
    │  - Meds     │                │   EHR       │               │  - Antithrombotic│
    │  - Problems │                │   Backend   │               │  - Consent prep  │
    │  - Labs     │                │             │               └──────────────────┘
    │  - Vitals   │                │   Python    │
    │  - Docs     │                │   FastAPI   │               ┌──────────────────┐
    └─────────────┘                │             │───────────────│  INTRA-OP        │
                                   │   FHIR R4   │               │  - Quick ref     │
    ┌─────────────┐                │   Transform │               │  - Imaging       │
    │  Ultralinq  │───────────────>│             │               │  - Allergies     │
    │  (Planned)  │                │             │               └──────────────────┘
    │  - Echo     │                │   WebSocket │
    │  - Vascular │                │   Realtime  │               ┌──────────────────┐
    │    labs     │                │             │───────────────│  POST-OP NOTES   │
    └─────────────┘                └─────────────┘               │  - Op note draft │
                                          │                      │  - Dictation aid │
    ┌─────────────┐                       │                      └──────────────────┘
    │  Imaging    │───────────────────────┘
    │  (Planned)  │                                              ┌──────────────────┐
    │  - CTA/MRA  │                                              │  QUALITY/VQI     │
    │  - Duplex   │                                              │  - Registry data │
    └─────────────┘                                              │  - Outcomes      │
                                                                 └──────────────────┘
                                                                         │
                                                                         v
                                                                 ┌──────────────────┐
                                                                 │ PLAUD/VASCULAR AI│
                                                                 │ - Transcription  │
                                                                 │ - AI Analysis    │
                                                                 └──────────────────┘
```

---

## How It Works

### The Golden Path: Athena → Extension → Backend → Frontend

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  ATHENA BROWSER  │     │ CHROME EXTENSION │     │  PYTHON BACKEND  │     │  REACT FRONTEND  │
│                  │     │                  │     │                  │     │                  │
│  Athena web app  │     │  interceptor.js  │     │     main.py      │     │ SurgicalDashboard│
│  makes API calls │────>│  captures resp   │────>│  transforms to   │────>│  displays        │
│                  │     │                  │     │  FHIR R4         │     │  clinical data   │
│  (We observe,    │     │  injector.js     │     │                  │     │                  │
│   don't modify)  │     │  bridges context │     │  narrative_engine│     │  NarrativeCard   │
│                  │     │                  │     │  generates text  │     │  shows AI output │
│                  │     │  background.js   │     │                  │     │                  │
│                  │     │  relays to /in.. │     │  WebSocket push  │     │  auto-updates    │
└──────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘

Key Principle: Data flows PASSIVELY. We OBSERVE Athena's own API responses.
              We do NOT inject requests or modify the EHR application.
```

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd shadow-ehr-bridge

# 2. Start the backend
cd backend
pip install -r requirements.txt
python main.py
# Backend runs at http://localhost:8000

# 3. Load the Chrome extension
# - Go to chrome://extensions
# - Enable Developer Mode
# - Click "Load unpacked"
# - Select the extension/ folder

# 4. Start the frontend (optional)
npm install
npm run dev
# Frontend runs at http://localhost:5173

# 5. Navigate to Athena
# - Open AthenaNet in Chrome
# - Browse patient charts
# - Data flows automatically to Shadow EHR
```

---

## Architecture Overview

| Layer | Component | Purpose |
|-------|-----------|---------|
| **Capture** | interceptor.js | Hooks fetch/XHR in Athena page context |
| **Bridge** | injector.js | Content script bridging page → extension |
| **Relay** | background.js | Service worker → HTTP POST to backend |
| **Process** | main.py | FastAPI, patient cache, WebSocket hub |
| **Transform** | fhir_converter.py | Raw Athena → FHIR R4 resources |
| **Synthesize** | vascular_parser.py | Surgeon-centric profiles, antithrombotic flags |
| **Narrate** | narrative_engine.py | LLM-generated surgical narratives |
| **Display** | SurgicalDashboard.tsx | Clinical dashboard with phase-based view |

---

## Key Features

### Antithrombotic Management
Automatically identifies and categorizes blood thinners:
- **Antiplatelets:** Aspirin, Clopidogrel (Plavix), Ticagrelor, Prasugrel
- **Anticoagulants:** Warfarin, DOACs (Xarelto, Eliquis, Pradaxa), Heparin

### Cardiovascular Risk Assessment
RCRI-like scoring based on extracted problem list:
- CAD, CHF, Diabetes, CKD, CVA, High-risk surgery

### Real-Time Updates
- WebSocket streaming from backend to frontend
- Patient data updates as you navigate in Athena
- No manual refresh needed

### AI-Powered Narratives
Gemini-generated pre-op summaries including:
- Patient demographics and history
- Surgical risk assessment
- Anticoagulation management recommendations
- Procedure-specific considerations

---

## API Reference

### WebSocket (Primary)
```
ws://localhost:8000/ws/frontend

Messages:
  PATIENT_UPDATE  - Patient data changed
  LOG_ENTRY       - API capture logged
  STATUS_UPDATE   - Connection status
  PING            - Heartbeat
```

### REST API
```
POST /ingest                    - Receive captured data
GET  /active/profile/{id}       - Get vascular profile
GET  /narrative/generate/{id}   - Generate pre-op narrative
GET  /health                    - Health check
```

---

## Configuration

### Environment Variables (.env)
```ini
# AI Provider (for narrative generation)
GEMINI_API_KEY=AIza...

# Backend
BACKEND_PORT=8000

# Frontend
VITE_API_URL=http://localhost:8000
```

### CORS (main.py)
If running frontend on different ports, update `allow_origins` in main.py:
```python
allow_origins=[
    "http://localhost:3000", "http://localhost:3001",
    "http://localhost:3002", "http://localhost:3003",
    "http://localhost:5173", "http://127.0.0.1:3000",
]
```

---

## Troubleshooting

### No Data Appearing
1. Check extension badge (should show "ON")
2. Check browser console for `[AthenaNet Bridge]` logs
3. Check backend terminal for "INCOMING ATHENA PAYLOAD"
4. Reload extension and refresh Athena tab

### CORS Errors
Update `allow_origins` in main.py to include your frontend port.

### Active Fetch Returns 500
Active fetch requires session headers from passive capture.
Navigate manually in Athena first, then try active fetch.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Complete system architecture, data flow diagrams, component deep dives |
| [INSTALL.md](INSTALL.md) | Detailed installation and configuration guide |

---

## Clinical Workflow Integration

### Pre-Op Clinic
1. Open patient in Athena
2. Shadow EHR captures data automatically
3. View synthesized pre-op narrative
4. Review antithrombotic management
5. Complete surgical consent

### Intra-Op
1. Quick reference for allergies, medications
2. Access imaging reports
3. Problem list for comorbidity awareness

### Post-Op
1. Dictate operative findings
2. Shadow EHR provides structured data for note
3. Export to Plaud for transcription

### Quality Reporting
1. Procedure data captured during workflow
2. Export to VQI-compatible format
3. Submit to registry

---

## Security Notes

- **Local Processing:** All data processing on localhost
- **PHI Handling:** Patient data in RAM only (ephemeral)
- **No Credentials:** System does not store login credentials
- **API Keys:** Never commit to version control
- **Session Data:** Used only for HTTP downloads (short-lived)

---

## Version

| Version | Changes |
|---------|---------|
| 2.1.0 | WebSocket data flow fix, CORS expansion, architecture documentation |
| 2.0.0 | 4-layer architecture, vascular surgery focus |
| 1.0.0 | Initial release |

---

## License

For research and educational purposes. Production clinical use requires regulatory compliance review.

---

*Maintainer: Vascular Surgery Informatics Team*
*Last Updated: 2026-01-02*
