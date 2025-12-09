# AthenaNet Shadow EHR: Autonomous Clinical Intelligence Layer
## System Architecture & Engineering Thesis

**Version:** 0.9.0 (Prototype)  
**Architecture:** Parasitic Overlay / Sidecar Pattern  
**Core Intelligence:** Gemini 2.5 Flash (Multi-Agent Swarm)

---

## 1. Abstract
The **AthenaNet Shadow EHR** is a high-fidelity software overlay designed to decouple clinical data utility from the underlying constraints of the AthenaHealth interface. By implementing a browser-based **Interceptor Layer** (Chrome Extension) and a local **Normalization Engine** (Python), the system creates a real-time, read/write-capable "Shadow Record." This record powers a **Multi-Agent Generative AI Swarm** that automates documentation, risk stratification, and coding in real-time, effectively functioning as an autonomous resident physician sitting between the surgeon and the raw EHR database.

## 2. System Topology

The system operates on a four-tier data pipeline:

### Tier 1: The Ingestion Layer (Chrome Extension)
*   **Mechanism:** `window.fetch` and `XMLHttpRequest` prototype interception.
*   **Strategy:** Unlike traditional scrapers that parse DOM (HTML), this system listens to the "wire." It intercepts the JSON payloads AthenaNet sends to its own frontend.
*   **Modes:**
    *   **Passive (Listener):** Captures data only as the physician navigates the chart.
    *   **Active (Vacuum):** Programmatically navigates the internal Athena router to "vacuum" specific endpoints (`/chart/patient/{id}/*`) without user interaction.

### Tier 2: The Normalization Engine (Python/Local)
*   **Role:** ETL (Extract, Transform, Load).
*   **Process:** Raw Athena JSON is noisy and UI-specific. The Python engine applies schema mapping to convert proprietary Athena objects into **FHIR-lite** (Fast Healthcare Interoperability Resources) compatible JSON.
*   **Output:** Cleaned, structured clinical objects (Patient, Encounter, Condition, Medication).

### Tier 3: The Data Hub (PlaudAI / PostgreSQL)
*   **Role:** Persistence & Provenance.
*   **Function:** Serves as the "Single Source of Truth" for the Shadow EHR.
*   **Mirror Ledger:** A cryptographic-style audit log (implemented in `MirrorLedger.tsx`) that records every read operation (scrape) and every write operation (AI generation) to ensure clinical defensibility.

### Tier 4: The Intelligence Layer (React + Gemini)
*   **Role:** Presentation & Cognitive Processing.
*   **Implementation:** A React-based Command Center (`App.tsx`) that visualizes the data and orchestrates the AI agents.

---

## 3. Frontend Engineering & Code Structure

The frontend (`/`) is built using **React 19** and **TypeScript**, emphasizing strict typing for medical data structures.

### 3.1 Core Components

#### `App.tsx` (The Orchestrator)
The root component acts as the central state machine. It manages three critical state verticals:
1.  **Connection State:** Is the Scraper Active or Passive? (`scraperMode`)
2.  **Clinical State:** The current Patient object in memory. (`currentPatient`)
3.  **Agent State:** The asynchronous "thinking" states of the AI swarm.

#### `services/geminiService.ts` (The Cortex)
This module interfaces with the Google Gemini API. It implements a **Stateless Request Pattern**:
*   It does not hold conversation history (chat).
*   It performs "Zero-Shot" or "Few-Shot" analysis on the JSON payload provided by the scraper.
*   **Safety:** It sets `temperature: 0.2` to minimize hallucinations, prioritizing deterministic output for medical safety.

#### `components/LiveLog.tsx` (The Nervous System)
Visualizes the raw data stream. It provides psychological reassurance to the user that the "Interceptor" is functioning. It uses a `ref`-based auto-scroll mechanism to handle high-velocity log events during "Active/Vacuum" mode.

#### `components/MirrorLedger.tsx` (The Audit Trail)
Implements the "Mirror Ledger" concept.
*   **Data Structure:** `hash`, `entity`, `action`, `timestamp`.
*   **Purpose:** In a clinical audit, this component proves *where* a suggestion came from. Did the AI hallucinate a diagnosis, or did it extract it from an intercepted API call 30ms prior? The Ledger provides the causal link.

### 3.2 Type Definitions (`types.ts`)
We utilize strict interfaces to enforce data integrity:
*   `Patient`: A composite interface aggregating Demographics, Conditions (ICD), and Meds (RxNorm-style strings).
*   `ScraperMode`: Enum controlling the behavior of the ingestion layer.

---

## 4. Multi-Agent Swarm Architecture

The system does not use a single "Chatbot." It uses specialized agents invoked in parallel (`Promise.all` pattern in `runAgents`):

1.  **Clinical Summarizer Agent:**
    *   *Input:* Demographics, Vitals, Notes.
    *   *System Prompt:* "Expert Medical Scribe."
    *   *Output:* SOAP Note formatted text.

2.  **Risk Predictor Agent:**
    *   *Input:* Conditions, Vitals, Labs.
    *   *System Prompt:* "Clinical Risk AI."
    *   *Output:* Calculated probability score + Rationale.

3.  **Coding Assistant Agent:**
    *   *Input:* Encounter Notes + Problem List.
    *   *System Prompt:* "Medical Coder (CPT/ICD-10)."
    *   *Output:* Billing codes.

## 5. Security & Compliance Strategy

*   **Local Execution:** The architecture favors local Python processing to minimize data egress.
*   **Ephemeral Frontend:** The React app holds patient data in memory (RAM) only. Refreshing the page clears the PHI (Protected Health Information). Persistence is handled solely by the secure backend (PlaudAI/Postgres).
*   **API Key Isolation:** The Gemini API key is injected via `process.env`, ensuring it is never hardcoded in the source.

---

## 6. Next Implementation Steps

1.  **Chrome Extension:** Scaffold `manifest.json` (Manifest V3) with `declarativeNetRequest` or `webRequest` permissions.
2.  **Python Socket Server:** Build the `FastAPI` or `Websocket` server to receive the extension's payload.
3.  **Bridge:** Replace `services/mockScraperService.ts` with a real `WebSocket` client that connects to `ws://localhost:8000`.

---

## 7. Implementation & Deployment Guide

This section outlines the operational requirements to deploy the Shadow EHR in a local environment.

### 7.1 Environment Prerequisites

The system is a hybrid application requiring two distinct runtimes:

1.  **JavaScript Runtime (Frontend):**
    *   **Node.js v18+**: Required to build the React application.
    *   **Package Manager**: `npm` or `yarn`.

2.  **Python Runtime (Backend/Scraper Engine):**
    *   **Conda Environment (Recommended):** Use the provided `environment.yml` to manage dependencies.
    *   **Python Version**: 3.10+
    *   **Key Libraries**: `fastapi`, `playwright`, `pydantic`.

### 7.2 Configuration (`.env`)

The application requires environment variables to secure sensitive credentials. Create a `.env` file in the project root:

```ini
# Required for Intelligence Layer
API_KEY=AIzaSy... (Your Google Gemini API Key)
```

### 7.3 Interaction with AthenaNet

**Crucial Operational Concept:** The Shadow EHR utilizes a "Session Piggybacking" technique.

*   **Does AthenaNet need to be open?** **YES.**
    You must have Google Chrome open with a tab logged into AthenaNet (`athenahealth.com`).
    
*   **Does the user need to log in?** **YES.**
    The system *does not* handle authentication (OAuth/2FA). It relies on the *existing, authenticated session* of the physician. 
    
    1.  **Login:** The physician logs into AthenaNet normally using their credentials and 2FA.
    2.  **Injection:** The Chrome Extension (once installed) automatically detects the active session tokens (cookies/headers).
    3.  **Interception:** When the physician views a patient, the extension "sees" the same data the browser sees and mirrors it to our Python backend.

### 7.4 Deployment Steps

1.  **Start the Backend (Python):**
    ```bash
    # 1. Create the environment
    conda env create -f environment.yml
    
    # 2. Activate it
    conda activate shadow-ehr
    
    # 3. CRITICAL: Install browser binaries for Playwright
    playwright install
    
    # 4. Run the server
    uvicorn main:app --reload --port 8000
    ```

2.  **Start the Frontend (React):**
    ```bash
    npm install
    npm start
    ```
    *The Command Center will open at `http://localhost:3000`.*

3.  **Load the Extension:**
    *   Go to `chrome://extensions`.
    *   Enable "Developer Mode".
    *   Click "Load Unpacked" and select the `/extension` folder (to be built).

4.  **Clinical Workflow:**
    *   Navigate to a patient chart in AthenaNet.
    *   Watch the **Shadow Command Center** (running on a second monitor) instantly populate with the patient's data.
