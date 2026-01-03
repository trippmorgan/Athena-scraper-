# Installation Guide: Shadow EHR Bridge

## Mission Context

This system captures clinical data from Athena EHR to support the vascular surgery workflow:
- **Pre-operative planning** and risk assessment
- **Intra-operative** decision support
- **Post-operative** documentation
- **Quality reporting** (VQI)
- **Export** to Plaud/Vascular AI

The core data flow MUST always work:
```
Athena → Extension → Backend → Frontend
```

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.10+ | Backend server |
| Node.js | 18+ | Frontend (optional) |
| Chrome | 120+ | Extension host |
| RAM | 8GB+ | Data processing |

---

## Part 1: Backend Setup

The backend is the heart of the system - it receives captured data, transforms it to FHIR R4, and broadcasts to frontends.

### Step 1.1: Install Dependencies

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Or install manually:
pip install fastapi uvicorn websockets pydantic python-dotenv httpx google-generativeai
```

### Step 1.2: Configure Environment

Create `.env` file in the backend directory:

```ini
# Required for AI narratives (optional - system works without)
GEMINI_API_KEY=AIza...

# Server config
BACKEND_PORT=8000
BACKEND_HOST=0.0.0.0
```

### Step 1.3: Start the Backend

```bash
cd backend
python main.py
```

You should see:
```
[INFO] Shadow EHR Backend starting...
[INFO] WebSocket hub ready on ws://localhost:8000/ws/frontend
[INFO] HTTP API ready on http://localhost:8000
[INFO] Waiting for Chrome extension connection...
```

### Step 1.4: Verify Backend

```bash
# Health check
curl http://localhost:8000/health

# Should return:
# {"status": "healthy", "extension_connected": false, "frontends_connected": 0}
```

---

## Part 2: Chrome Extension Setup

The extension captures Athena API responses and relays them to the backend.

### Step 2.1: Load the Extension

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Select the `extension/` folder from this repository

### Step 2.2: Verify Extension Load

- Extension card should appear with name "AthenaNet Clinical Bridge"
- No errors should show (click "Errors" if visible)
- Click the extension icon to see popup

### Step 2.3: Test Connection

1. With backend running, the extension badge should show connection status
2. Open browser DevTools on any Athena page
3. Look for logs: `[AthenaNet Bridge] Connected to backend`

---

## Part 3: Frontend Setup (Optional)

The React frontend displays captured data in a surgical workflow context.

### Step 3.1: Install Dependencies

```bash
# From repository root
npm install
```

### Step 3.2: Start Development Server

```bash
npm run dev
```

Frontend runs at `http://localhost:5173` (or next available port).

### Step 3.3: Verify Frontend

1. Open `http://localhost:5173` in browser
2. Check browser console for WebSocket connection:
   ```
   [Shadow EHR Frontend] WEBSOCKET CONNECTED TO BACKEND
   ```
3. Navigate to a patient in Athena - data should appear in frontend

---

## Part 4: Verification Checklist

### Complete System Test

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Start backend | Logs show "WebSocket hub ready" |
| 2 | Load extension | Badge appears, no errors |
| 3 | Start frontend | WebSocket connected |
| 4 | Open Athena | Extension logs: "Athena tab detected" |
| 5 | Open patient chart | Backend logs: "INCOMING ATHENA PAYLOAD" |
| 6 | Check frontend | Patient data displayed |

### Log Locations

| Component | Location |
|-----------|----------|
| Backend | Terminal where `python main.py` runs |
| Extension | Chrome DevTools → Console (on Athena tab) |
| Frontend | Browser DevTools → Console (on frontend tab) |

---

## Troubleshooting

### Backend Won't Start

```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
kill -9 $(lsof -t -i:8000)

# Restart
python main.py
```

### Extension Not Connecting

1. Reload extension: chrome://extensions → refresh icon
2. Check extension console for errors
3. Verify backend is running: `curl http://localhost:8000/health`

### No Data in Frontend

1. Check WebSocket connection in frontend console
2. Verify extension is capturing: check Athena tab console
3. Check backend logs for incoming payloads

### CORS Errors

If frontend runs on a different port, update `allow_origins` in `backend/main.py`:

```python
allow_origins=[
    "http://localhost:3000", "http://localhost:3001",
    "http://localhost:3002", "http://localhost:3003",
    "http://localhost:5173", "http://127.0.0.1:3000",
]
```

### Active Fetch Returns 500

Active fetch requires session headers captured from passive intercepts:
1. Navigate manually in Athena first (passive capture builds session)
2. Then try active fetch buttons
3. This is a known limitation - session header capture improvement is planned

---

## File Structure

```
shadow-ehr-bridge/
├── backend/
│   ├── main.py               # FastAPI server, WebSocket hub
│   ├── fhir_converter.py     # Raw → FHIR R4 transformation
│   ├── vascular_parser.py    # Surgeon-centric profile builder
│   ├── narrative_engine.py   # LLM narrative generation
│   └── requirements.txt      # Python dependencies
│
├── extension/
│   ├── manifest.json         # Chrome MV3 manifest
│   ├── background.js         # Service worker - data relay
│   ├── injector.js           # Content script - bridge
│   ├── interceptor.js        # Page context - API capture
│   ├── activeFetcher.js      # Active data fetch
│   ├── popup.html            # Extension popup
│   └── popup.js              # Popup controller
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
├── ARCHITECTURE.md           # System architecture docs
├── README.md                 # Quick start guide
└── INSTALL.md                # This file
```

---

## Data Flow (Critical Path)

```
1. interceptor.js     Hooks fetch/XHR in Athena page
                      ↓
2. injector.js        Bridges page context to extension
                      ↓
3. background.js      HTTP POST to backend /ingest
                      ↓
4. main.py            Processes, transforms, caches
                      ↓
5. fhir_converter.py  Raw Athena → FHIR R4
                      ↓
6. WebSocket          PATIENT_UPDATE to all frontends
                      ↓
7. SurgicalDashboard  Displays synthesized data
```

**Rule:** This data flow MUST work even if AI features are disabled or fail.

---

## Next Steps After Installation

1. **Test passive capture** - Browse Athena normally, watch data flow
2. **Check vascular profile** - View antithrombotic categorization
3. **Generate narrative** - Click "Generate Pre-Op Narrative" (requires Gemini key)
4. **Monitor endpoint discovery** - Check backend logs for captured patterns

---

## Security Notes

- All processing is local (localhost only)
- PHI is held in RAM only (ephemeral)
- No credentials are stored or captured
- API keys should never be committed to version control
- Session cookies used only for HTTP downloads (short-lived)

---

*Last Updated: 2026-01-02*
*See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system documentation*
