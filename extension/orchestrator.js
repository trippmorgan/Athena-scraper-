/**
 * EHR Bridge AI Team Orchestrator
 *
 * ORGANIZATIONAL STRUCTURE:
 * ┌─────────────────────────────────────────────────────────┐
 * │                    CLAUDE (CEO)                         │
 * │  Chief Intelligence Officer                             │
 * │  - Session state detection                              │
 * │  - Traffic pattern recognition                          │
 * │  - Strategic orchestration                              │
 * │  - HIPAA compliance oversight                           │
 * │  - Agent task delegation                                │
 * └─────────────────────┬───────────────────────────────────┘
 *                       │
 *          ┌────────────┴────────────┐
 *          ▼                         ▼
 * ┌─────────────────────┐   ┌─────────────────────┐
 * │   GEMINI (CTO)      │   │   CODEX (Principal) │
 * │   Data Scientist    │   │   DevOps Engineer   │
 * │                     │   │                     │
 * │ - Clinical data     │   │ - Endpoint config   │
 * │   processing        │   │   generation        │
 * │ - FHIR conversion   │   │ - Fetch logic       │
 * │ - Medical context   │   │ - API integration   │
 * │ - Summary generation│   │ - Code scaffolding  │
 * └─────────────────────┘   └─────────────────────┘
 */

// Orchestrator logging
const OrchestratorLogger = {
  _log: (level, emoji, agent, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Orchestrator ${time}]`;
    const agentColors = {
      ceo: '#8b5cf6',      // Purple for Claude
      cto: '#10b981',      // Green for Gemini
      principal: '#f97316', // Orange for Codex
      system: '#6b7280'     // Gray for system
    };
    const color = agentColors[agent] || agentColors.system;
    const style = `color: ${color}; font-weight: bold;`;

    data
      ? console.log(`%c${prefix} ${emoji} [${agent.toUpperCase()}] ${msg}`, style, data)
      : console.log(`%c${prefix} ${emoji} [${agent.toUpperCase()}] ${msg}`, style);
  },
  ceo: (msg, data) => OrchestratorLogger._log('info', '👔', 'ceo', msg, data),
  cto: (msg, data) => OrchestratorLogger._log('info', '🔬', 'cto', msg, data),
  principal: (msg, data) => OrchestratorLogger._log('info', '🛠️', 'principal', msg, data),
  system: (msg, data) => OrchestratorLogger._log('info', '⚙️', 'system', msg, data),
  decision: (msg, data) => OrchestratorLogger._log('info', '🎯', 'ceo', msg, data),
  delegation: (from, to, task) => {
    console.log(`%c[Orchestrator] 📋 ${from.toUpperCase()} → ${to.toUpperCase()}: ${task}`,
      'color: #3b82f6; font-weight: bold;');
  }
};

class EHRBridgeOrchestrator {
  constructor(config = {}) {
    this.config = config;

    // Session state (CEO tracks this)
    this.sessionState = {
      athenaLoggedIn: false,
      currentPatientMRN: null,
      captureMode: 'passive',
      sessionHealth: 'unknown',
      discoveredEndpoints: [],
      lastActivity: null
    };

    // Agent configurations
    this.agents = {
      claude: {
        role: 'CEO',
        title: 'Chief Intelligence Officer',
        model: 'claude-sonnet-4-20250514',
        endpoint: 'https://api.anthropic.com/v1/messages',
        status: 'idle',
        lastTask: null,
        responsibilities: [
          'session_detection',
          'traffic_orchestration',
          'strategic_decisions',
          'hipaa_oversight',
          'agent_coordination'
        ],
        systemPrompt: `You are the CEO/Chief Intelligence Officer of the EHR Bridge AI Team.

Your responsibilities:
1. SESSION DETECTION: Analyze browser data to determine if user is logged into Athena EHR
2. TRAFFIC ORCHESTRATION: Decide which network requests contain valuable clinical data
3. STRATEGIC DECISIONS: Plan optimal data extraction strategies for surgical workflows
4. HIPAA OVERSIGHT: Flag potential compliance issues before data storage
5. AGENT COORDINATION: Delegate tasks to Gemini (clinical processing) or Codex (code generation)

CONTEXT: This system supports vascular surgeons who need:
- Anticoagulation status (critical for surgery timing)
- Renal function (for contrast decisions)
- Cardiac clearance status
- Previous vascular interventions

Always respond with structured JSON. Be concise and decisive.`
      },

      gemini: {
        role: 'CTO',
        title: 'Chief Data Scientist',
        model: 'gemini-2.0-flash',
        endpoint: 'https://generativelanguage.googleapis.com/v1beta/models',
        status: 'idle',
        lastTask: null,
        responsibilities: [
          'clinical_data_processing',
          'fhir_transformation',
          'medical_context_extraction',
          'summary_generation',
          'medication_analysis',
          'lab_interpretation'
        ],
        systemPrompt: `You are the CTO/Chief Data Scientist of the EHR Bridge AI Team.

Your responsibilities:
1. CLINICAL DATA PROCESSING: Extract structured data from raw Athena API responses
2. FHIR TRANSFORMATION: Convert proprietary formats to FHIR R4 standard
3. MEDICAL CONTEXT: Add clinical interpretation to raw values
4. SUMMARY GENERATION: Create vascular surgery-focused pre-op summaries

FOCUS AREAS for vascular surgery:
- Anticoagulants/antiplatelets: warfarin, apixaban, rivaroxaban, clopidogrel, aspirin
- Renal function: Cr, eGFR, BUN (critical for contrast decisions)
- Coagulation: PT/INR, PTT
- Cardiac: EF, stress test results, clearance status

Output structured JSON matching clinical data standards. Be precise with medical terminology.`
      },

      codex: {
        role: 'Principal',
        title: 'Principal DevOps Engineer',
        model: 'gpt-4-turbo',
        endpoint: 'https://api.openai.com/v1/chat/completions',
        status: 'idle',
        lastTask: null,
        responsibilities: [
          'endpoint_discovery',
          'fetch_logic_generation',
          'api_integration_code',
          'parser_creation',
          'extension_modifications'
        ],
        systemPrompt: `You are the Principal DevOps Engineer of the EHR Bridge AI Team.

Your responsibilities:
1. ENDPOINT DISCOVERY: Analyze captured traffic to identify reusable API patterns
2. FETCH LOGIC: Generate JavaScript functions to replay captured requests
3. PARSER CREATION: Build extractors for specific clinical data types
4. EXTENSION CODE: Create Chrome extension enhancements

OUTPUT FORMAT for endpoint patterns:
{
  "pattern": "/api/chart/{patientId}/medications",
  "method": "GET",
  "headers": {...},
  "responseSchema": {...}
}

OUTPUT FORMAT for fetch functions:
async function fetchXXX(patientId, sessionCookies) { ... }

Write clean, production-ready JavaScript. Include error handling and retry logic.`
      }
    };

    // Task queue for agent coordination
    this.taskQueue = [];
    this.taskHistory = [];
    this.agentResults = {
      claude: [],
      gemini: [],
      codex: []
    };

    // Endpoint pattern registry (Codex maintains this)
    this.endpointRegistry = new Map();

    // Initialize
    this._init();
  }

  async _init() {
    OrchestratorLogger.system('EHR Bridge AI Team initializing...');

    // Load API keys from storage
    await this._loadApiKeys();

    // Check agent health
    await this._checkAgentHealth();

    OrchestratorLogger.system('Orchestrator ready', {
      agents: Object.keys(this.agents),
      sessionState: this.sessionState
    });
  }

  async _loadApiKeys() {
    try {
      const result = await chrome.storage.local.get([
        'anthropicApiKey',
        'geminiApiKey',
        'openaiApiKey'
      ]);

      this.config.claudeApiKey = result.anthropicApiKey;
      this.config.geminiApiKey = result.geminiApiKey;
      this.config.openaiApiKey = result.openaiApiKey;

      OrchestratorLogger.system('API keys loaded', {
        claude: !!result.anthropicApiKey,
        gemini: !!result.geminiApiKey,
        codex: !!result.openaiApiKey
      });
    } catch (e) {
      OrchestratorLogger.system('Failed to load API keys', e.message);
    }
  }

  async _checkAgentHealth() {
    const healthStatus = {};

    for (const [name, agent] of Object.entries(this.agents)) {
      const hasKey = name === 'claude' ? !!this.config.claudeApiKey :
                     name === 'gemini' ? !!this.config.geminiApiKey :
                     !!this.config.openaiApiKey;

      healthStatus[name] = hasKey ? 'ready' : 'no_api_key';
      agent.status = hasKey ? 'idle' : 'offline';
    }

    return healthStatus;
  }

  // ============================================================
  // CEO FUNCTIONS - Claude handles strategic decisions
  // ============================================================

  /**
   * CEO FUNCTION: Detect Athena Login State
   * Claude monitors for authentication indicators in debug data
   */
  async detectAthenaSession(debuggerData) {
    OrchestratorLogger.ceo('Analyzing session state...');

    const sessionIndicators = {
      cookies: this._extractCookies(debuggerData),
      authHeaders: this._extractAuthHeaders(debuggerData),
      urlPatterns: this._extractUrlPatterns(debuggerData),
      timestamp: new Date().toISOString()
    };

    const claudeAnalysis = await this._askClaude({
      task: 'session_detection',
      prompt: `Analyze this browser debug data to determine:
1. Is the user logged into Athena EHR?
2. What authentication tokens/cookies are present?
3. What is the current patient context (if any)?
4. Are there any session expiration risks?
5. Session health: good, warning, or expired?

Debug Data:
${JSON.stringify(sessionIndicators, null, 2)}

Respond with JSON:
{
  "isLoggedIn": boolean,
  "sessionHealth": "good" | "warning" | "expired",
  "authTokens": ["list of token names found"],
  "currentPatient": "MRN or null",
  "expirationRisk": boolean,
  "recommendations": ["action items"]
}`
    });

    if (claudeAnalysis.success) {
      const analysis = claudeAnalysis.parsed;
      this.sessionState.athenaLoggedIn = analysis.isLoggedIn;
      this.sessionState.currentPatientMRN = analysis.currentPatient;
      this.sessionState.sessionHealth = analysis.sessionHealth;
      this.sessionState.lastActivity = new Date().toISOString();

      OrchestratorLogger.ceo('Session analysis complete', analysis);
    }

    return claudeAnalysis;
  }

  /**
   * CEO FUNCTION: Analyze and Route Network Traffic
   * Claude decides what to capture and who should process it
   */
  async analyzeTraffic(networkRequest) {
    OrchestratorLogger.ceo('Analyzing traffic...', {
      url: networkRequest.url?.substring(0, 60)
    });

    const trafficAnalysis = await this._askClaude({
      task: 'traffic_orchestration',
      prompt: `Analyze this network request and decide:
1. Is this an Athena API call worth recording?
2. What data category does it contain?
3. Should we extract an endpoint pattern for future use?
4. Any HIPAA concerns with storing this data?
5. Which agent should process this?

Request:
URL: ${networkRequest.url}
Method: ${networkRequest.method}
Response Type: ${networkRequest.responseType}
Response Size: ${networkRequest.responseSize} bytes

Respond with JSON:
{
  "shouldRecord": boolean,
  "dataCategory": "medication" | "lab" | "problem" | "vital" | "document" | "imaging" | "note" | "unknown",
  "endpointPattern": "regex pattern or null",
  "hipaaCompliant": boolean,
  "hipaaConcerns": ["list any concerns"],
  "delegateTo": "gemini" | "codex" | "both" | "none",
  "priority": "high" | "medium" | "low",
  "reasoning": "brief explanation"
}`
    });

    if (trafficAnalysis.success && trafficAnalysis.parsed.shouldRecord) {
      const analysis = trafficAnalysis.parsed;

      // CEO delegation logic
      if (analysis.delegateTo === 'gemini' || analysis.delegateTo === 'both') {
        OrchestratorLogger.delegation('CEO', 'CTO', `Process ${analysis.dataCategory} data`);
        this._queueTask('gemini', 'process_clinical_data', {
          category: analysis.dataCategory,
          request: networkRequest,
          priority: analysis.priority
        });
      }

      if (analysis.delegateTo === 'codex' || analysis.delegateTo === 'both') {
        OrchestratorLogger.delegation('CEO', 'Principal', `Extract endpoint pattern`);
        this._queueTask('codex', 'extract_endpoint_pattern', {
          url: networkRequest.url,
          method: networkRequest.method,
          pattern: analysis.endpointPattern
        });
      }
    }

    return trafficAnalysis;
  }

  /**
   * CEO FUNCTION: Plan Data Extraction Strategy
   * Claude creates an optimal plan for extracting patient data
   */
  async planExtractionStrategy(patientMRN) {
    OrchestratorLogger.ceo('Planning extraction strategy for MRN:', patientMRN);

    const strategy = await this._askClaude({
      task: 'strategic_decisions',
      prompt: `Plan a complete data extraction strategy for patient MRN: ${patientMRN}

Available discovered endpoints:
${JSON.stringify(Array.from(this.endpointRegistry.values()), null, 2)}

Current session state:
${JSON.stringify(this.sessionState, null, 2)}

As CEO, create an extraction plan for a vascular surgeon who needs:
- Anticoagulation status (CRITICAL - affects surgery timing)
- Renal function (for contrast decisions)
- Previous vascular interventions
- Cardiac clearance status
- Current medications
- Recent labs

Respond with JSON:
{
  "fetchSequence": [
    {"endpoint": "string", "priority": 1-5, "canParallelize": boolean, "assignTo": "gemini"}
  ],
  "rateLimitMs": number,
  "estimatedDuration": "string",
  "criticalData": ["list of must-have data points"],
  "fallbackStrategy": "string",
  "agentAssignments": {
    "gemini": ["task1", "task2"],
    "codex": ["task1"]
  }
}`
    });

    if (strategy.success) {
      OrchestratorLogger.decision('Extraction strategy created', strategy.parsed);
    }

    return strategy;
  }

  // ============================================================
  // CTO FUNCTIONS - Gemini handles clinical data processing
  // ============================================================

  /**
   * CTO FUNCTION: Process Clinical Data
   * Gemini extracts structured data from raw Athena responses
   */
  async processClinicalData(category, rawData) {
    OrchestratorLogger.cto(`Processing ${category} data...`);
    this.agents.gemini.status = 'processing';

    const taskPrompts = {
      medication: `Extract medications from this data, focusing on:
- Anticoagulants: warfarin, apixaban, rivaroxaban, dabigatran, edoxaban
- Antiplatelets: clopidogrel, aspirin, ticagrelor, prasugrel
- Flag last refill dates for adherence assessment
- Note any hold instructions

Output JSON:
{
  "medications": [{
    "name": "string",
    "dose": "string",
    "frequency": "string",
    "route": "string",
    "lastFill": "date",
    "isAnticoagulant": boolean,
    "isAntiplatelet": boolean,
    "holdDays": number | null
  }],
  "anticoagulationStatus": "on" | "held" | "none",
  "bridgingRequired": boolean
}`,

      lab: `Extract lab values, prioritizing:
- Renal: Creatinine, eGFR, BUN (critical for contrast)
- Coagulation: PT, INR, PTT (for anticoagulation management)
- CBC: Hgb, Plt (surgical planning)
- Metabolic: K, Na, Glucose

Output JSON:
{
  "labs": [{
    "name": "string",
    "value": number,
    "unit": "string",
    "referenceRange": "string",
    "isAbnormal": boolean,
    "collectionDate": "date"
  }],
  "renalFunction": {
    "creatinine": number,
    "egfr": number,
    "stage": "normal" | "stage1" | "stage2" | "stage3a" | "stage3b" | "stage4" | "stage5"
  },
  "coagulation": {
    "inr": number,
    "therapeutic": boolean
  }
}`,

      problem: `Extract problems/diagnoses, categorizing for vascular surgery:
- Vascular: PAD, CAD, AAA, carotid stenosis, DVT/PE history
- Cardiac: CHF, arrhythmias, valve disease
- Metabolic: DM, CKD, HTN, HLD
- Other surgical risks

Output JSON:
{
  "problems": [{
    "name": "string",
    "icd10": "string",
    "status": "active" | "resolved" | "chronic",
    "category": "vascular" | "cardiac" | "metabolic" | "other",
    "surgicalRelevance": "high" | "medium" | "low"
  }],
  "vascularHistory": ["list of vascular conditions"],
  "cardiacRisk": "low" | "intermediate" | "high"
}`
    };

    const prompt = taskPrompts[category] || `Extract structured clinical data from:
${JSON.stringify(rawData, null, 2)}

Output as structured JSON.`;

    const result = await this._callGemini(prompt, rawData);

    this.agents.gemini.status = 'idle';
    this.agents.gemini.lastTask = category;
    this.agentResults.gemini.push({ category, result, timestamp: new Date().toISOString() });

    return result;
  }

  /**
   * CTO FUNCTION: Generate Surgical Summary
   * Gemini creates a vascular surgery-focused pre-op summary
   */
  async generateSurgicalSummary(patientData) {
    OrchestratorLogger.cto('Generating surgical summary...');
    this.agents.gemini.status = 'summarizing';

    const result = await this._callGemini(`Generate a vascular surgery pre-op summary from this patient data:
${JSON.stringify(patientData, null, 2)}

Structure the summary as:

# PRE-OPERATIVE SUMMARY

## ANTICOAGULATION STATUS (CRITICAL)
- Current regimen
- Last dose
- Recommended hold period
- Bridging requirements

## RENAL FUNCTION
- Latest Cr/eGFR
- CKD stage
- Contrast precautions needed

## CARDIAC RISK
- Ejection fraction (if known)
- Recent stress test
- Clearance status
- RCRI score estimate

## RELEVANT ANATOMY
- Previous vascular procedures
- Known stenoses/occlusions
- Relevant imaging findings

## COMORBIDITIES
- High-risk conditions for surgery
- Medication considerations

## RECOMMENDATIONS
- Pre-op optimization needed
- Day-of-surgery medication instructions
- Anesthesia considerations`);

    this.agents.gemini.status = 'idle';
    return result;
  }

  /**
   * CTO FUNCTION: FHIR Transformation
   * Gemini converts proprietary Athena data to FHIR R4
   */
  async transformToFHIR(rawData, resourceType) {
    OrchestratorLogger.cto(`Transforming to FHIR ${resourceType}...`);

    const result = await this._callGemini(`Convert this Athena EHR data to FHIR R4 ${resourceType} resource:
${JSON.stringify(rawData, null, 2)}

Follow FHIR R4 specification strictly. Include:
- Proper resource type and ID
- All required fields
- Appropriate coding systems (ICD-10, SNOMED, RxNorm, LOINC)
- Extensions for Athena-specific data

Output valid FHIR JSON.`);

    return result;
  }

  // ============================================================
  // PRINCIPAL ENGINEER FUNCTIONS - Codex handles code generation
  // ============================================================

  /**
   * PRINCIPAL FUNCTION: Extract Endpoint Pattern
   * Codex analyzes traffic to discover reusable API patterns
   */
  async extractEndpointPattern(networkRequest) {
    OrchestratorLogger.principal('Extracting endpoint pattern...', {
      url: networkRequest.url?.substring(0, 50)
    });
    this.agents.codex.status = 'analyzing';

    const result = await this._callCodex(`Analyze this Athena API request and generate:
1. A reusable endpoint pattern (with {placeholders} for dynamic parts)
2. Required headers for authentication
3. Response schema based on the data type

Request:
URL: ${networkRequest.url}
Method: ${networkRequest.method}
Headers: ${JSON.stringify(networkRequest.headers || {})}

Output JSON:
{
  "pattern": "/api/chart/{patientId}/medications",
  "regex": "^\\/api\\/chart\\/\\d+\\/medications$",
  "method": "GET",
  "requiredHeaders": {
    "X-Requested-With": "XMLHttpRequest"
  },
  "dynamicParams": ["patientId"],
  "dataCategory": "medication" | "lab" | "problem" | etc,
  "responseSchema": {
    "type": "object",
    "properties": {...}
  },
  "notes": "any special handling needed"
}`);

    if (result.success) {
      // Register the discovered pattern
      const pattern = result.parsed || result.content;
      if (pattern.pattern) {
        this.endpointRegistry.set(pattern.pattern, {
          ...pattern,
          discoveredAt: new Date().toISOString(),
          useCount: 0
        });
        this.sessionState.discoveredEndpoints.push(pattern.pattern);
        OrchestratorLogger.principal('Pattern registered:', pattern.pattern);
      }
    }

    this.agents.codex.status = 'idle';
    this.agents.codex.lastTask = 'endpoint_discovery';

    return result;
  }

  /**
   * PRINCIPAL FUNCTION: Generate Fetch Logic
   * Codex creates reusable JavaScript functions for data fetching
   */
  async generateFetchLogic(endpointPattern, options = {}) {
    OrchestratorLogger.principal('Generating fetch logic for:', endpointPattern);
    this.agents.codex.status = 'coding';

    const result = await this._callCodex(`Generate a reusable JavaScript fetch function for this endpoint pattern:

Pattern: ${endpointPattern}
Options: ${JSON.stringify(options)}

Requirements:
1. Use the authenticated session cookies (credentials: 'include')
2. Include proper error handling with retry logic
3. Add request timeout (30 seconds)
4. Parse response based on data type
5. Return structured data matching the expected schema

Output a complete, production-ready JavaScript module:

/**
 * Fetch [description] from Athena API
 * @param {string} patientId - Patient MRN
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} Parsed response
 */
async function fetch[Name](patientId, options = {}) {
  // Implementation
}

// Include the parser function too
function parse[Name]Response(rawData) {
  // Implementation
}

module.exports = { fetch[Name], parse[Name]Response };`);

    this.agents.codex.status = 'idle';
    this.agents.codex.lastTask = 'fetch_generation';
    this.agentResults.codex.push({ pattern: endpointPattern, result, timestamp: new Date().toISOString() });

    return result;
  }

  /**
   * PRINCIPAL FUNCTION: Generate Vascular Parser
   * Codex creates specialized parsers for vascular surgery data
   */
  async generateVascularParser(sampleData) {
    OrchestratorLogger.principal('Generating vascular surgery parser...');
    this.agents.codex.status = 'coding';

    const result = await this._callCodex(`Create a specialized parser for vascular surgery data extraction.

Sample input data:
${JSON.stringify(sampleData, null, 2)}

Required output fields for vascular surgeons:
- anticoagulants: array of {drug, dose, lastFill, holdDays}
- antiplatelets: array of {drug, dose}
- renalFunction: {creatinine, egfr, date, contrastSafe}
- coagulation: {inr, ptt, plateletCount, bleedingRisk}
- cardiacStatus: {ef, stressTest, clearance, metsCapacity}
- vascularHistory: array of {procedure, location, date, findings}
- accessSites: {leftRadial, rightRadial, leftFemoral, rightFemoral} with patency status

Output TypeScript/JavaScript code with:
1. Type definitions
2. Parser function
3. Validation logic
4. Default values for missing data

Make it defensive - handle missing/malformed data gracefully.`);

    this.agents.codex.status = 'idle';
    return result;
  }

  // ============================================================
  // PRIVATE API METHODS
  // ============================================================

  async _askClaude(request) {
    if (!this.config.claudeApiKey) {
      OrchestratorLogger.ceo('No API key configured');
      return { success: false, error: 'Claude API key not configured' };
    }

    this.agents.claude.status = 'thinking';

    try {
      // Route through background worker (uses existing infrastructure)
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({
          type: 'CLAUDE_API_REQUEST',
          payload: {
            apiKey: this.config.claudeApiKey,
            messages: [{ role: 'user', content: request.prompt }],
            systemPrompt: this.agents.claude.systemPrompt,
            model: this.agents.claude.model,
            temperature: 0.2,
            maxTokens: 2048
          }
        }, (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });

      this.agents.claude.status = 'idle';
      this.agents.claude.lastTask = request.task;

      // Try to parse JSON from response
      let parsed = null;
      try {
        const content = result.content || '';
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          parsed = JSON.parse(jsonMatch[0]);
        }
      } catch (e) {
        // JSON parsing failed, return raw content
      }

      return {
        success: result.success,
        content: result.content,
        parsed,
        usage: result.usage
      };

    } catch (error) {
      this.agents.claude.status = 'error';
      OrchestratorLogger.ceo('API call failed:', error.message);
      return { success: false, error: error.message };
    }
  }

  async _callGemini(prompt, contextData = null) {
    if (!this.config.geminiApiKey) {
      OrchestratorLogger.cto('No API key configured');
      return { success: false, error: 'Gemini API key not configured' };
    }

    this.agents.gemini.status = 'processing';

    try {
      const fullPrompt = contextData
        ? `${prompt}\n\nData to process:\n${JSON.stringify(contextData, null, 2)}`
        : prompt;

      const response = await fetch(
        `${this.agents.gemini.endpoint}/${this.agents.gemini.model}:generateContent?key=${this.config.geminiApiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts: [{ text: fullPrompt }] }],
            systemInstruction: { parts: [{ text: this.agents.gemini.systemPrompt }] },
            generationConfig: {
              temperature: 0.2,
              maxOutputTokens: 8192,
              responseMimeType: 'application/json'
            }
          })
        }
      );

      if (!response.ok) {
        throw new Error(`Gemini API error: ${response.status}`);
      }

      const data = await response.json();
      const content = data.candidates?.[0]?.content?.parts?.[0]?.text || '';

      this.agents.gemini.status = 'idle';

      // Try to parse JSON
      let parsed = null;
      try {
        parsed = JSON.parse(content);
      } catch (e) {
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          parsed = JSON.parse(jsonMatch[0]);
        }
      }

      OrchestratorLogger.cto('Response received', {
        contentLength: content.length,
        parsed: !!parsed
      });

      return { success: true, content, parsed };

    } catch (error) {
      this.agents.gemini.status = 'error';
      OrchestratorLogger.cto('API call failed:', error.message);
      return { success: false, error: error.message };
    }
  }

  async _callCodex(prompt) {
    if (!this.config.openaiApiKey) {
      OrchestratorLogger.principal('No API key configured');
      return { success: false, error: 'OpenAI API key not configured' };
    }

    this.agents.codex.status = 'coding';

    try {
      const response = await fetch(this.agents.codex.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.config.openaiApiKey}`
        },
        body: JSON.stringify({
          model: this.agents.codex.model,
          messages: [
            { role: 'system', content: this.agents.codex.systemPrompt },
            { role: 'user', content: prompt }
          ],
          temperature: 0.1,
          max_tokens: 4096
        })
      });

      if (!response.ok) {
        throw new Error(`OpenAI API error: ${response.status}`);
      }

      const data = await response.json();
      const content = data.choices?.[0]?.message?.content || '';

      this.agents.codex.status = 'idle';

      // Try to parse JSON if present
      let parsed = null;
      try {
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          parsed = JSON.parse(jsonMatch[0]);
        }
      } catch (e) {
        // Code output, not JSON
      }

      OrchestratorLogger.principal('Response received', {
        contentLength: content.length
      });

      return { success: true, content, parsed };

    } catch (error) {
      this.agents.codex.status = 'error';
      OrchestratorLogger.principal('API call failed:', error.message);
      return { success: false, error: error.message };
    }
  }

  // ============================================================
  // TASK QUEUE MANAGEMENT
  // ============================================================

  _queueTask(agent, task, data) {
    this.taskQueue.push({
      id: `${agent}_${Date.now()}`,
      agent,
      task,
      data,
      status: 'pending',
      createdAt: new Date().toISOString()
    });
  }

  async processTaskQueue() {
    while (this.taskQueue.length > 0) {
      const task = this.taskQueue.shift();
      task.status = 'processing';

      OrchestratorLogger.system(`Processing task: ${task.task} for ${task.agent}`);

      try {
        let result;

        switch (task.agent) {
          case 'gemini':
            result = await this.processClinicalData(task.data.category, task.data.request);
            break;
          case 'codex':
            result = await this.extractEndpointPattern(task.data);
            break;
          default:
            result = { error: 'Unknown agent' };
        }

        task.status = 'completed';
        task.result = result;
        this.taskHistory.push(task);

      } catch (error) {
        task.status = 'failed';
        task.error = error.message;
        this.taskHistory.push(task);
      }
    }
  }

  // ============================================================
  // UTILITY METHODS
  // ============================================================

  _extractCookies(debuggerData) {
    if (!debuggerData?.cookies) return [];
    return debuggerData.cookies.filter(c =>
      c.name.toLowerCase().includes('athena') ||
      c.name.toLowerCase().includes('session') ||
      c.name.toLowerCase().includes('auth') ||
      c.name.toLowerCase().includes('token')
    );
  }

  _extractAuthHeaders(debuggerData) {
    if (!debuggerData?.headers) return [];
    return Object.entries(debuggerData.headers || {})
      .filter(([name]) =>
        name.toLowerCase().includes('authorization') ||
        name.toLowerCase().includes('x-csrf') ||
        name.toLowerCase().includes('x-auth') ||
        name.toLowerCase().includes('x-request')
      )
      .map(([name, value]) => ({ name, value: value.substring(0, 20) + '...' }));
  }

  _extractUrlPatterns(debuggerData) {
    if (!debuggerData?.requests) return [];
    return debuggerData.requests
      .map(r => r.url)
      .filter(url =>
        url.includes('athena') ||
        url.includes('/api/') ||
        url.includes('/chart/') ||
        url.includes('/ax/')
      )
      .slice(0, 20); // Limit to 20 most recent
  }

  // ============================================================
  // PUBLIC STATUS METHODS
  // ============================================================

  getTeamStatus() {
    return {
      sessionState: this.sessionState,
      agents: Object.fromEntries(
        Object.entries(this.agents).map(([name, agent]) => [
          name,
          {
            role: agent.role,
            title: agent.title,
            status: agent.status,
            lastTask: agent.lastTask,
            hasApiKey: name === 'claude' ? !!this.config.claudeApiKey :
                       name === 'gemini' ? !!this.config.geminiApiKey :
                       !!this.config.openaiApiKey
          }
        ])
      ),
      taskQueue: this.taskQueue.length,
      endpointsDiscovered: this.endpointRegistry.size,
      taskHistory: this.taskHistory.slice(-10) // Last 10 tasks
    };
  }

  getDiscoveredEndpoints() {
    return Array.from(this.endpointRegistry.entries());
  }

  getAgentResults(agent) {
    return this.agentResults[agent] || [];
  }
}

// Export for use in extension
if (typeof window !== 'undefined') {
  window.EHRBridgeOrchestrator = EHRBridgeOrchestrator;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { EHRBridgeOrchestrator };
}

console.log('%c[Orchestrator] ✅ EHR Bridge AI Team Orchestrator loaded',
  'color: #8b5cf6; font-weight: bold; font-size: 14px;');
