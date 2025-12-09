# AthenaNet Shadow EHR: Autonomous Clinical Intelligence Overlay
## System Architecture & Engineering Thesis

**Version:** 0.9.2 (Alpha)
**Architecture:** Parasitic Browser-Based Overlay (Sidecar Pattern)
**Core Intelligence:** Google Gemini 2.5 Flash (Multi-Agent Swarm)

---

## 1. Abstract: The Case for Parasitic Interoperability

Contemporary Electronic Health Records (EHRs) act as semantic silos, trapping high-value clinical data within proprietary, non-interoperable interfaces. The **AthenaNet Shadow EHR** proposes a novel architectural paradigm: **Parasitic Interoperability**. Instead of relying on slow, permissioned HL7/FHIR interfaces provided by the vendor, this system acts as a benevolent parasite on the host application (AthenaNet).

By injecting a listener into the browser's execution context, the system achieves **Read-Write capability** on the live clinical data stream without requiring backend integration. This creates a "Shadow Record"—a real-time, normalized Digital Twin of the patient chart—which serves as the grounding context for a swarm of Generative AI agents. These agents function as an autonomous clinical support layer, performing documentation, risk stratification, and coding tasks in parallel with the human physician's workflow.

---

## 2. Architectural Topology

The system implements a four-tier data pipeline designed to minimize latency (<100ms wire-to-agent) and maximize semantic fidelity.

### 2.1 Data Flow Logic

1.  **Origin:** AthenaNet React Frontend initiates an HTTP request.
2.  **Interception:** Chrome Content Script (`injected.js`) hooks the `window.fetch` prototype.
3.  **Extraction:** The JSON payload is cloned and serialized before the browser renders it.
4.  **Transmission:** Data is piped via a persistent WebSocket to the local Python Engine.
5.  **Normalization:** Python converts proprietary Athena JSON to **FHIR R4** resources.
6.  **Inference:** The React Command Center dispatches the FHIR object to the **Gemini 2.5 Flash** swarm.
7.  **Output:** Clinical insights are rendered on the Command Center UI.

### 2.2 Tier 1: The Ingestion Layer (Browser Context)
*   **Mechanism:** Prototype Mutation (Monkey Patching).
*   **Implementation:** The system injects a content script into the "Main World" of the browser tab. It overwrites `window.fetch` and `XMLHttpRequest.prototype.open/send`.
*   **Capabilities:**
    *   **Transparency:** The host application (Athena) is unaware of the interception.
    *   **Full Fidelity:** The interceptor captures the exact JSON payloads used to render the official UI, bypassing any "public API" data loss.
    *   **Active Navigation:** In "Vacuum Mode," the extension can programmatically drive the host router to visit specific patient sub-pages (Labs, Imaging) to hydrate the Shadow Record fully.

### 2.3 Tier 2: The Normalization Engine (Python/FastAPI)
*   **Role:** ETL (Extract, Transform, Load) & Semantic Mapping.
*   **Challenge:** AthenaNet internal APIs return non-standard, UI-optimized JSON with irregular keys and deeply nested structures.
*   **Solution:** The Python backend implements a robust **Schema Mapper** that:
    *   Flattens nested arrays.
    *   Normalizes dates to ISO-8601.
    *   Maps proprietary medication IDs to RxNorm concepts (where possible).
    *   Constructs valid **FHIR R4** resources (Patient, Observation, Condition).
*   **Latency Control:** Uses `FastAPI` and `uvicorn` for high-concurrency asynchronous processing.

### 2.4 Tier 3: The Intelligence Layer (Multi-Agent Swarm)
The system eschews a monolithic LLM approach in favor of a **Mixture of Agents (MoA)** architecture. The React frontend acts as the orchestrator, dispatching data to specialized prompts running on **Gemini 2.5 Flash**.

| Agent Identity | Cognitive Role | Input Vector | Output Artifact |
| :--- | :--- | :--- | :--- |
| **Clinical Summarizer** | Synthesis | Notes, Vitals, Labs | SOAP Note (Text) |
| **Risk Predictor** | Probabilistic Inference | Chronic Conditions, Meds | Risk Score (0-100) + Rationale |
| **Coding Assistant** | Semantic Translation | Diagnosis List, Procedures | ICD-10 / CPT Codes |

### 2.5 Tier 4: The Mirror Ledger (Provenance & Audit)
To address the "Black Box" problem of Generative AI, the system implements a **Mirror Ledger**.
*   **Structure:** An append-only, cryptographic-style log of every atomic operation.
*   **Function:** Traces every AI-generated insight back to the specific intercepted JSON packet that grounded it.
*   **Compliance:** Ensures that no hallucination goes undetected; every claim in the generated output has a pointer to source data in the capture log.

---

## 3. Operational Modes

### Mode A: Passive Listener (The "Scribe")
*   **Behavior:** The system remains silent, capturing only the data the physician explicitly views.
*   **Use Case:** Real-time documentation assistance during a patient visit.
*   **Load Impact:** Zero.

### Mode B: Active Vacuum (The "Crawler")
*   **Behavior:** The system utilizes the Chrome Extension's scripting privileges to fetch background resources.
*   **Process:** When a patient is loaded, the vacuum automatically requests `/chart/patient/{id}/labs`, `/medications`, and `/imaging` in parallel background threads.
*   **Use Case:** Pre-visit chart prep; population health analytics.

---

## 4. Security & Privacy Thesis

The architecture is designed around **Data Sovereignty** and **Ephemeral Processing**.

1.  **Local-First Execution:** The Python Normalization Engine runs on `localhost`. Patient data is processed within the hospital's firewall (on the physician's machine).
2.  **Ephemeral Frontend:** The React Command Center holds PHI in volatile memory (RAM). A browser refresh purges the session.
3.  **No Persistence (Default):** The system does not write to a third-party database by default. Persistence is opt-in via the PlaudAI connector.
4.  **API Key Isolation:** The LLM interface uses environment-injected keys (`process.env.API_KEY`), ensuring credentials never touch the source code or the browser bundle.

---

## 5. Engineering Manual: Deployment & Configuration

### 5.1 Prerequisites
*   **Node.js v18+**: For the React Command Center.
*   **Python 3.10+**: For the Normalization Engine.
*   **Google Chrome**: The host environment.

### 5.2 The Environment
The project uses `Conda` for Python dependency isolation and `npm` for the frontend.

**File:** `environment.yml`
```yaml
name: shadow-ehr
dependencies:
  - python=3.10
  - pip
  - pip:
    - fastapi
    - uvicorn
    - pydantic
    - websockets
    - playwright
    - psycopg2-binary
```

### 5.3 Installation Sequence

**Phase 1: Backend Initialization**
```bash
# 1. Create the Conda environment
conda env create -f environment.yml

# 2. Activate the environment
conda activate shadow-ehr

# 3. CRITICAL: Install Playwright browsers (Required for Active Mode)
playwright install

# 4. Create .env file for Intelligence Layer
echo "API_KEY=your_gemini_key_here" > .env

# 5. Ignite the Engine
uvicorn main:app --reload --port 8000
```

**Phase 2: Frontend Initialization**
```bash
# In a new terminal
npm install
npm start
# Access Command Center at http://localhost:3000
```

**Phase 3: The Interceptor Injection**
1.  Open Chrome to `chrome://extensions`.
2.  Enable **Developer Mode**.
3.  Click **Load Unpacked**.
4.  Select the `extension/` directory.

### 5.4 The "Piggyback" Protocol
The system requires an active, authenticated AthenaNet session.
1.  Log in to `athenahealth.com` in Chrome.
2.  The Extension will detect the session cookies automatically.
3.  Open the Shadow Command Center (`localhost:3000`) in a secondary window/monitor.
4.  Navigate AthenaNet normally. The Shadow EHR will mirror the data instantly.
