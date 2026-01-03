/**
 * EHR Bridge - Chrome Extension Background Script
 *
 * CLAUDE (CEO) - Session Detection & Traffic Orchestration
 *
 * This script runs in the background and:
 * 1. Detects when you're logged into Athena
 * 2. Uses Chrome Debugger API to record all traffic
 * 3. Sends traffic patterns to Claude for analysis
 * 4. Delegates data processing to Gemini/Codex
 */

// ============ LOGGING ============

const CEOLogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[CEO ${time}]`;
    const styles = {
      info: "color: #8b5cf6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      decision: "color: #3b82f6; font-weight: bold;",
      delegate: "color: #f97316; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data)
         : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => CEOLogger._log('info', '👔', msg, data),
  success: (msg, data) => CEOLogger._log('success', '✅', msg, data),
  warn: (msg, data) => CEOLogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => CEOLogger._log('error', '❌', msg, data),
  decision: (msg, data) => CEOLogger._log('decision', '🎯', msg, data),
  delegate: (to, task) => CEOLogger._log('delegate', '📋', `Delegating to ${to}: ${task}`)
};

// ============ CONFIGURATION ============

const CONFIG = {
  athenaPatterns: [
    '*://athenanet.athenahealth.com/*',
    '*://*.athenahealth.com/*',
    '*://app.athenahealth.com/*'
  ],
  apiKeys: {
    claude: null,
    gemini: null,
    openai: null
  },
  backendUrl: 'http://localhost:8000',
  debugMode: true
};

// ============ STATE MANAGEMENT ============

const state = {
  athenaTabId: null,
  debuggerAttached: false,
  isRecording: false,
  capturedRequests: [],
  discoveredEndpoints: new Map(),
  sessionInfo: null,
  pendingRequests: new Map(), // Track requests waiting for response body
  stats: {
    totalCaptured: 0,
    apiCallsAnalyzed: 0,
    delegatedToGemini: 0,
    delegatedToCodex: 0,
    endpointsDiscovered: 0
  }
};

// ============ INITIALIZATION ============

async function initializeCEO() {
  CEOLogger.info('CEO (Claude) initializing...');

  // Load API keys from storage
  const stored = await chrome.storage.local.get([
    'anthropicApiKey',
    'geminiApiKey',
    'openaiApiKey',
    'discoveredEndpoints',
    'ceoStats'
  ]);

  CONFIG.apiKeys.claude = stored.anthropicApiKey;
  CONFIG.apiKeys.gemini = stored.geminiApiKey;
  CONFIG.apiKeys.openai = stored.openaiApiKey;

  if (stored.discoveredEndpoints) {
    state.discoveredEndpoints = new Map(stored.discoveredEndpoints);
  }

  if (stored.ceoStats) {
    state.stats = { ...state.stats, ...stored.ceoStats };
  }

  CEOLogger.success('CEO initialized', {
    hasClaudeKey: !!CONFIG.apiKeys.claude,
    hasGeminiKey: !!CONFIG.apiKeys.gemini,
    hasCodexKey: !!CONFIG.apiKeys.openai,
    discoveredEndpoints: state.discoveredEndpoints.size
  });

  // Start monitoring for Athena tabs
  monitorAthenaTabs();
}

// ============ ATHENA TAB MONITORING ============

function monitorAthenaTabs() {
  // Check existing tabs
  chrome.tabs.query({}, (tabs) => {
    for (const tab of tabs) {
      if (isAthenaUrl(tab.url)) {
        CEOLogger.info('Found existing Athena tab', { tabId: tab.id, url: tab.url });
        handleAthenaTab(tab.id);
      }
    }
  });

  // Monitor new tabs and updates
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.url && isAthenaUrl(tab.url)) {
      CEOLogger.info('Athena tab updated', { tabId, url: tab.url });
      handleAthenaTab(tabId);
    }
  });

  // Clean up when tabs close
  chrome.tabs.onRemoved.addListener((tabId) => {
    if (tabId === state.athenaTabId) {
      CEOLogger.warn('Athena tab closed, detaching debugger');
      state.athenaTabId = null;
      state.debuggerAttached = false;
      state.sessionInfo = null;
    }
  });
}

function isAthenaUrl(url) {
  if (!url) return false;
  return url.includes('athenahealth.com') || url.includes('athenanet');
}

async function handleAthenaTab(tabId) {
  state.athenaTabId = tabId;

  // Detect session
  const sessionInfo = await detectAthenaSession(tabId);

  // Auto-attach debugger if recording is enabled and we're logged in
  if (state.isRecording && sessionInfo.isLoggedIn && !state.debuggerAttached) {
    await attachDebugger(tabId);
  }

  // Notify popup/UI
  broadcastMessage('SESSION_UPDATE', sessionInfo);
}

// ============ SESSION DETECTION (CEO Core Function) ============

async function detectAthenaSession(tabId) {
  CEOLogger.decision('Analyzing Athena session...');

  try {
    // Get cookies
    const cookies = await chrome.cookies.getAll({
      domain: '.athenahealth.com'
    });

    const sessionCookies = cookies.filter(c =>
      c.name.toLowerCase().includes('session') ||
      c.name.toLowerCase().includes('auth') ||
      c.name.toLowerCase().includes('jsessionid') ||
      c.name.toLowerCase().includes('token')
    );

    // Get tab info
    const tab = await chrome.tabs.get(tabId);

    // Build session data for analysis
    const sessionData = {
      url: tab.url,
      title: tab.title,
      cookies: sessionCookies.map(c => ({
        name: c.name,
        expirationDate: c.expirationDate,
        secure: c.secure,
        httpOnly: c.httpOnly
      })),
      cookieCount: sessionCookies.length,
      timestamp: new Date().toISOString()
    };

    // If Claude API key is configured, get intelligent analysis
    if (CONFIG.apiKeys.claude) {
      const analysis = await askClaudeCEO('session_analysis', sessionData);
      state.sessionInfo = analysis;

      if (analysis.isLoggedIn) {
        CEOLogger.success('Session detected: LOGGED IN', {
          health: analysis.sessionHealth,
          concerns: analysis.concerns?.length || 0
        });
      } else {
        CEOLogger.warn('Session analysis: NOT LOGGED IN');
      }

      return analysis;
    }

    // Fallback: Basic detection without Claude
    const basicAnalysis = {
      isLoggedIn: sessionCookies.length >= 2,
      sessionHealth: sessionCookies.length >= 3 ? 'good' :
                     sessionCookies.length >= 1 ? 'warning' : 'expired',
      concerns: [],
      recommendations: ['Configure Claude API key for intelligent session analysis'],
      fallback: true
    };

    state.sessionInfo = basicAnalysis;
    CEOLogger.info('Basic session detection (Claude not configured)', basicAnalysis);

    return basicAnalysis;

  } catch (error) {
    CEOLogger.error('Session detection failed', error.message);
    return {
      isLoggedIn: false,
      sessionHealth: 'error',
      error: error.message
    };
  }
}

// ============ CHROME DEBUGGER API (CEO Traffic Recording) ============

async function attachDebugger(tabId) {
  if (state.debuggerAttached) {
    CEOLogger.warn('Debugger already attached');
    return true;
  }

  try {
    // Request debugger permission
    await chrome.debugger.attach({ tabId }, '1.3');

    // Enable network monitoring
    await chrome.debugger.sendCommand({ tabId }, 'Network.enable');

    // Disable cache to ensure we capture fresh requests
    await chrome.debugger.sendCommand({ tabId }, 'Network.setCacheDisabled', {
      cacheDisabled: true
    });

    state.debuggerAttached = true;
    state.athenaTabId = tabId;

    CEOLogger.success('Debugger attached successfully', { tabId });

    await logCEOAction('debugger_attached', { tabId });
    broadcastMessage('DEBUGGER_STATUS', { attached: true, tabId });

    return true;

  } catch (error) {
    CEOLogger.error('Failed to attach debugger', error.message);
    broadcastMessage('DEBUGGER_STATUS', { attached: false, error: error.message });
    return false;
  }
}

async function detachDebugger() {
  if (!state.debuggerAttached || !state.athenaTabId) {
    return;
  }

  try {
    await chrome.debugger.detach({ tabId: state.athenaTabId });
    state.debuggerAttached = false;
    CEOLogger.info('Debugger detached');
    broadcastMessage('DEBUGGER_STATUS', { attached: false });
  } catch (error) {
    CEOLogger.error('Failed to detach debugger', error.message);
  }
}

// ============ DEBUGGER EVENT HANDLING ============

chrome.debugger.onEvent.addListener(async (source, method, params) => {
  if (source.tabId !== state.athenaTabId) return;
  if (!state.isRecording) return;

  switch (method) {
    case 'Network.requestWillBeSent':
      handleRequestWillBeSent(source.tabId, params);
      break;

    case 'Network.responseReceived':
      await handleResponseReceived(source.tabId, params);
      break;

    case 'Network.loadingFinished':
      await handleLoadingFinished(source.tabId, params);
      break;
  }
});

function handleRequestWillBeSent(tabId, params) {
  const { requestId, request, timestamp, type } = params;

  // Only track API calls
  if (!isAthenaApiCall(request.url)) return;

  // Store pending request info
  state.pendingRequests.set(requestId, {
    url: request.url,
    method: request.method,
    headers: request.headers,
    postData: request.postData,
    timestamp: timestamp,
    type: type
  });
}

async function handleResponseReceived(tabId, params) {
  const { requestId, response, timestamp } = params;

  if (!state.pendingRequests.has(requestId)) return;

  const requestInfo = state.pendingRequests.get(requestId);

  // Add response info
  requestInfo.response = {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
    mimeType: response.mimeType,
    timestamp: timestamp
  };

  state.pendingRequests.set(requestId, requestInfo);
}

async function handleLoadingFinished(tabId, params) {
  const { requestId, encodedDataLength, timestamp } = params;

  if (!state.pendingRequests.has(requestId)) return;

  const requestInfo = state.pendingRequests.get(requestId);
  requestInfo.encodedDataLength = encodedDataLength;
  requestInfo.finishedAt = timestamp;

  try {
    // Get response body
    const bodyResult = await chrome.debugger.sendCommand(
      { tabId },
      'Network.getResponseBody',
      { requestId }
    );

    requestInfo.body = bodyResult.body;
    requestInfo.base64Encoded = bodyResult.base64Encoded;

  } catch (error) {
    // Body might not be available for some requests
    requestInfo.bodyError = error.message;
  }

  // Process the complete request with Claude CEO
  await processRequestWithClaude(requestInfo);

  // Clean up pending request
  state.pendingRequests.delete(requestId);
}

// ============ API CALL DETECTION ============

function isAthenaApiCall(url) {
  if (!url) return false;

  const apiPatterns = [
    '/api/',
    '/ax/',
    '/chart/',
    '/clinical/',
    '/patient/',
    '/medication/',
    '/lab/',
    '/document/',
    '/problem/',
    '/encounter/',
    '/allergy/',
    '/vital/',
    '/order/',
    '/result/',
    '/imaging/',
    '/note/'
  ];

  // Check for Athena domain first
  if (!url.includes('athena')) return false;

  return apiPatterns.some(pattern => url.includes(pattern));
}

// ============ TRAFFIC ANALYSIS (CEO Core Function) ============

async function processRequestWithClaude(request) {
  state.stats.totalCaptured++;

  // Create lightweight request summary for analysis
  const requestSummary = {
    url: request.url,
    method: request.method,
    status: request.response?.status,
    contentType: request.response?.mimeType,
    size: request.encodedDataLength,
    hasBody: !!request.body,
    bodyPreview: request.body?.substring(0, 500)
  };

  CEOLogger.info('Processing captured request', {
    url: request.url.substring(0, 80),
    status: request.response?.status
  });

  let analysis;

  if (CONFIG.apiKeys.claude) {
    // Get intelligent analysis from Claude CEO
    analysis = await askClaudeCEO('traffic_analysis', requestSummary);
    state.stats.apiCallsAnalyzed++;
  } else {
    // Fallback: Rule-based analysis
    analysis = ruleBasedAnalysis(request);
  }

  // Enrich request with analysis
  request.ceoAnalysis = analysis;

  // Store captured request
  state.capturedRequests.push({
    ...request,
    capturedAt: new Date().toISOString()
  });

  // Limit memory - keep last 500 requests
  if (state.capturedRequests.length > 500) {
    state.capturedRequests = state.capturedRequests.slice(-500);
  }

  // Extract endpoint pattern if valuable
  if (analysis.extractEndpoint) {
    await discoverEndpointPattern(request, analysis);
  }

  // Delegate to appropriate agent
  if (analysis.delegateTo && request.body) {
    await delegateTask(analysis.delegateTo, analysis.task, request);
  }

  // Forward to backend
  await forwardToBackend(request, analysis);

  // Broadcast update
  broadcastMessage('REQUEST_CAPTURED', {
    url: request.url,
    analysis: analysis,
    stats: state.stats
  });
}

function ruleBasedAnalysis(request) {
  const url = request.url.toLowerCase();

  let dataType = 'unknown';
  let delegateTo = null;
  let task = null;

  // Determine data type from URL
  if (url.includes('medication')) {
    dataType = 'medication';
    delegateTo = 'gemini';
    task = 'process_medications';
  } else if (url.includes('lab') || url.includes('result')) {
    dataType = 'lab';
    delegateTo = 'gemini';
    task = 'process_labs';
  } else if (url.includes('problem') || url.includes('diagnosis')) {
    dataType = 'problem';
    delegateTo = 'gemini';
    task = 'process_problems';
  } else if (url.includes('allergy')) {
    dataType = 'allergy';
    delegateTo = 'gemini';
    task = 'process_allergies';
  } else if (url.includes('vital')) {
    dataType = 'vital';
    delegateTo = 'gemini';
    task = 'process_vitals';
  } else if (url.includes('document') || url.includes('note')) {
    dataType = 'document';
  } else if (url.includes('imaging')) {
    dataType = 'imaging';
  }

  return {
    shouldRecord: true,
    dataType: dataType,
    extractEndpoint: true,
    hipaaSafe: !url.includes('ssn') && !url.includes('password'),
    delegateTo: delegateTo,
    task: task,
    fallback: true
  };
}

// ============ ENDPOINT DISCOVERY (CEO + Codex) ============

async function discoverEndpointPattern(request, analysis) {
  // Extract pattern from URL
  const pattern = extractEndpointPattern(request.url);

  // Check if we already have this pattern
  if (state.discoveredEndpoints.has(pattern.normalized)) {
    // Update use count
    const existing = state.discoveredEndpoints.get(pattern.normalized);
    existing.useCount++;
    existing.lastSeen = new Date().toISOString();
    return;
  }

  // New pattern discovered
  const endpointInfo = {
    pattern: pattern.normalized,
    original: request.url,
    method: request.method,
    dataType: analysis.dataType,
    headers: request.headers,
    responseSchema: null, // Codex will generate this
    discoveredAt: new Date().toISOString(),
    lastSeen: new Date().toISOString(),
    useCount: 1
  };

  state.discoveredEndpoints.set(pattern.normalized, endpointInfo);
  state.stats.endpointsDiscovered++;

  CEOLogger.success('New endpoint pattern discovered', {
    pattern: pattern.normalized,
    dataType: analysis.dataType
  });

  // Ask Codex to generate fetch logic and parser
  if (CONFIG.apiKeys.openai) {
    CEOLogger.delegate('Codex', 'extract_endpoint');
    await delegateTask('codex', 'extract_endpoint', {
      url: request.url,
      pattern: pattern.normalized,
      method: request.method,
      headers: request.headers,
      sampleResponse: request.body?.substring(0, 2000)
    });
  }

  // Persist discovered endpoints
  await chrome.storage.local.set({
    discoveredEndpoints: Array.from(state.discoveredEndpoints.entries())
  });

  broadcastMessage('ENDPOINT_DISCOVERED', endpointInfo);
}

function extractEndpointPattern(url) {
  try {
    const urlObj = new URL(url);
    let pathname = urlObj.pathname;

    // Replace numeric IDs with placeholders
    pathname = pathname
      .replace(/\/\d+\//g, '/{id}/')
      .replace(/\/\d+$/g, '/{id}');

    // Replace UUIDs with placeholders
    pathname = pathname.replace(
      /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
      '/{uuid}'
    );

    // Remove query string for pattern
    const normalized = `${urlObj.host}${pathname}`;

    return {
      normalized,
      original: url,
      hasParams: pathname.includes('{'),
      queryParams: Object.fromEntries(urlObj.searchParams)
    };

  } catch (error) {
    return { normalized: url, original: url, hasParams: false };
  }
}

// ============ AGENT DELEGATION ============

async function delegateTask(agent, task, data) {
  switch (agent) {
    case 'gemini':
      state.stats.delegatedToGemini++;
      CEOLogger.delegate('Gemini (CTO)', task);
      return await delegateToGemini(task, data);

    case 'codex':
      state.stats.delegatedToCodex++;
      CEOLogger.delegate('Codex (Principal)', task);
      return await delegateToCodex(task, data);

    default:
      CEOLogger.warn('Unknown agent for delegation', agent);
  }
}

async function delegateToGemini(task, data) {
  if (!CONFIG.apiKeys.gemini) {
    CEOLogger.warn('Gemini API key not configured');
    return null;
  }

  const taskPrompts = {
    process_medications: `You are the CTO/Chief Data Scientist. Extract medication data from this Athena response.
Focus on:
- Anticoagulants: warfarin, apixaban, rivaroxaban, dabigatran, edoxaban
- Antiplatelets: clopidogrel, aspirin, ticagrelor, prasugrel
- Include: name, dose, frequency, route, last fill date
- Flag anticoagulants/antiplatelets with holdDays for surgery

Data:
${typeof data.body === 'string' ? data.body : JSON.stringify(data)}

Return JSON: {medications: [{name, dose, frequency, route, lastFill, isAnticoagulant, isAntiplatelet, holdDays}]}`,

    process_labs: `You are the CTO/Chief Data Scientist. Extract laboratory values from this Athena response.
Prioritize for vascular surgery:
- Renal: Creatinine, eGFR, BUN
- Coagulation: PT, INR, PTT
- CBC: Hemoglobin, Platelets
- Metabolic: Potassium, Sodium

Data:
${typeof data.body === 'string' ? data.body : JSON.stringify(data)}

Return JSON: {labs: [{name, value, unit, date, isAbnormal, referenceRange}], renalFunction: {cr, egfr, stage}}`,

    process_problems: `You are the CTO/Chief Data Scientist. Extract problems/diagnoses from this Athena response.
Categorize for vascular surgery relevance:
- Vascular: PAD, CAD, AAA, carotid stenosis, DVT/PE
- Cardiac: CHF, arrhythmias, valve disease
- Metabolic: DM, CKD, HTN
- Other surgical risks

Data:
${typeof data.body === 'string' ? data.body : JSON.stringify(data)}

Return JSON: {problems: [{name, icd10, status, category, surgicalRelevance}]}`,

    process_vitals: `Extract vital signs for surgical assessment:
${typeof data.body === 'string' ? data.body : JSON.stringify(data)}

Return JSON: {vitals: [{name, value, unit, date}], bloodPressure: {systolic, diastolic}, heartRate, weight, bmi}`,

    process_allergies: `Extract allergies, especially drug allergies relevant to surgery:
${typeof data.body === 'string' ? data.body : JSON.stringify(data)}

Return JSON: {allergies: [{allergen, reaction, severity, isContrast, isAntibiotic, isLatex}]}`
  };

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${CONFIG.apiKeys.gemini}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: taskPrompts[task] || `Process this clinical data:\n${JSON.stringify(data)}` }] }],
          generationConfig: {
            temperature: 0.2,
            responseMimeType: 'application/json'
          }
        })
      }
    );

    if (!response.ok) {
      throw new Error(`Gemini API error: ${response.status}`);
    }

    const result = await response.json();
    const content = result.candidates?.[0]?.content?.parts?.[0]?.text;

    CEOLogger.success('Gemini processed data', { task });

    // Forward to backend
    await fetch(`${CONFIG.backendUrl}/ai/gemini-result`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, result: content, timestamp: new Date().toISOString() })
    }).catch(() => {}); // Non-blocking

    broadcastMessage('GEMINI_RESULT', { task, result: content });

    return content;

  } catch (error) {
    CEOLogger.error('Gemini delegation failed', error.message);
    return null;
  }
}

async function delegateToCodex(task, data) {
  if (!CONFIG.apiKeys.openai) {
    CEOLogger.warn('OpenAI/Codex API key not configured');
    return null;
  }

  const taskPrompts = {
    extract_endpoint: `You are the Principal DevOps Engineer. Analyze this Athena API endpoint and generate:
1. Reusable endpoint pattern with {placeholders}
2. Required headers for authentication
3. Expected response schema
4. Fetch function code

Endpoint data:
${JSON.stringify(data, null, 2)}

Return JSON:
{
  "pattern": "/api/chart/{patientId}/medications",
  "method": "GET",
  "requiredHeaders": {"X-Requested-With": "XMLHttpRequest"},
  "responseSchema": {type: "object", properties: {...}},
  "fetchFunction": "async function fetchMedications(patientId) {...}"
}`,

    generate_parser: `Create a TypeScript parser for this Athena response type:
${JSON.stringify(data, null, 2)}

Include type definitions and extraction logic.`,

    generate_fetcher: `Generate a complete fetch module for these discovered endpoints:
${JSON.stringify(Array.from(state.discoveredEndpoints.values()), null, 2)}

Include error handling, retry logic, and response parsing.`
  };

  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${CONFIG.apiKeys.openai}`
      },
      body: JSON.stringify({
        model: 'gpt-4-turbo',
        messages: [
          {
            role: 'system',
            content: 'You are a Principal DevOps Engineer specializing in Chrome extensions and EHR integration. Output clean, production-ready code.'
          },
          {
            role: 'user',
            content: taskPrompts[task] || `Generate code for:\n${JSON.stringify(data)}`
          }
        ],
        temperature: 0.1,
        max_tokens: 4096
      })
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status}`);
    }

    const result = await response.json();
    const content = result.choices?.[0]?.message?.content;

    CEOLogger.success('Codex generated code', { task });

    broadcastMessage('CODEX_RESULT', { task, result: content });

    return content;

  } catch (error) {
    CEOLogger.error('Codex delegation failed', error.message);
    return null;
  }
}

// ============ CLAUDE CEO API CALLS ============

async function askClaudeCEO(task, data) {
  if (!CONFIG.apiKeys.claude) {
    return { error: 'Claude API key not configured', fallback: true };
  }

  const systemPrompts = {
    session_analysis: `You are the CEO of an EHR Bridge system. Analyze this Athena session data and determine:

1. Is the user logged in? (isLoggedIn: boolean)
2. Session health (sessionHealth: 'good' | 'warning' | 'expired')
3. Security concerns (concerns: string[])
4. Recommendations (recommendations: string[])

Be concise and decisive. Respond with valid JSON only.`,

    traffic_analysis: `You are the CEO orchestrating EHR data extraction for vascular surgeons. Analyze this network request:

1. Should we record this? (shouldRecord: boolean)
2. Clinical data type? (dataType: 'medication' | 'lab' | 'problem' | 'vital' | 'allergy' | 'document' | 'imaging' | 'note' | 'unknown')
3. Extract endpoint pattern? (extractEndpoint: boolean)
4. HIPAA safe to store? (hipaaSafe: boolean)
5. Delegate to which agent? (delegateTo: 'gemini' | 'codex' | null)
6. Task for that agent? (task: string)

Focus on data valuable for vascular surgery pre-op assessment:
- Anticoagulation status
- Renal function
- Cardiac risk
- Vascular history

Respond with valid JSON only.`,

    strategy: `You are the CEO planning data extraction for a vascular surgery patient. Given discovered endpoints and session state:

1. Optimal fetch order (fetchOrder: array of endpoints)
2. Which can run in parallel (parallelGroups: array of arrays)
3. Rate limiting (rateLimitMs: number)
4. Critical must-have data (criticalEndpoints: array)
5. Fallback approach (fallbackStrategy: string)

Respond with valid JSON only.`
  };

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': CONFIG.apiKeys.claude,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1024,
        system: systemPrompts[task],
        messages: [{
          role: 'user',
          content: typeof data === 'string' ? data : JSON.stringify(data)
        }]
      })
    });

    if (!response.ok) {
      throw new Error(`Claude API error: ${response.status}`);
    }

    const result = await response.json();
    const content = result.content?.[0]?.text;

    // Parse JSON response
    try {
      return JSON.parse(content);
    } catch {
      // Try to extract JSON from response
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
      return { content, parseError: true };
    }

  } catch (error) {
    CEOLogger.error('Claude CEO analysis failed', error.message);
    return { error: error.message, fallback: true };
  }
}

// ============ BACKEND COMMUNICATION ============

async function forwardToBackend(request, analysis) {
  try {
    await fetch(`${CONFIG.backendUrl}/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Source': 'ceo-debugger'
      },
      body: JSON.stringify({
        url: request.url,
        method: request.method,
        status: request.response?.status,
        data: request.body,
        ceoAnalysis: analysis,
        timestamp: new Date().toISOString(),
        source: 'ceo-debugger'
      })
    });
  } catch (error) {
    // Non-blocking - backend might be offline
  }
}

// ============ EXTRACTION STRATEGY EXECUTION ============

async function executeExtractionStrategy(mrn) {
  CEOLogger.decision('Executing extraction strategy for MRN:', mrn);

  if (!state.sessionInfo?.isLoggedIn) {
    return { error: 'Not logged into Athena', success: false };
  }

  // Get strategy from Claude CEO
  const strategy = await askClaudeCEO('strategy', {
    mrn,
    discoveredEndpoints: Array.from(state.discoveredEndpoints.values()),
    sessionInfo: state.sessionInfo
  });

  if (strategy.error) {
    // Fallback: Use all discovered endpoints
    strategy.fetchOrder = Array.from(state.discoveredEndpoints.values())
      .filter(e => e.dataType !== 'unknown')
      .map(e => ({ pattern: e.pattern, dataType: e.dataType }));
    strategy.rateLimitMs = 500;
  }

  CEOLogger.info('Executing strategy', {
    endpoints: strategy.fetchOrder?.length || 0,
    rateLimit: strategy.rateLimitMs
  });

  const results = {};

  for (const endpoint of strategy.fetchOrder || []) {
    try {
      // Build URL from pattern
      const url = endpoint.pattern
        .replace('{id}', mrn)
        .replace('{patientId}', mrn)
        .replace('{mrn}', mrn);

      const response = await fetch(url, {
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      if (response.ok) {
        const data = await response.json();
        results[endpoint.dataType] = data;

        // Process with Gemini if clinical data
        if (['medication', 'lab', 'problem', 'vital', 'allergy'].includes(endpoint.dataType)) {
          await delegateToGemini(`process_${endpoint.dataType}s`, { body: JSON.stringify(data) });
        }
      }

      // Rate limiting
      await new Promise(r => setTimeout(r, strategy.rateLimitMs || 500));

    } catch (error) {
      results[endpoint.dataType] = { error: error.message };
    }
  }

  CEOLogger.success('Extraction complete', {
    successful: Object.keys(results).filter(k => !results[k].error).length,
    failed: Object.keys(results).filter(k => results[k].error).length
  });

  return { success: true, results };
}

// ============ UTILITIES ============

function broadcastMessage(type, data) {
  chrome.runtime.sendMessage({ type, data }).catch(() => {});
}

async function logCEOAction(action, details) {
  const log = {
    timestamp: new Date().toISOString(),
    action,
    details
  };

  const stored = await chrome.storage.local.get('ceo_audit_log') || {};
  const logs = stored.ceo_audit_log || [];
  logs.push(log);

  // Keep last 1000 logs
  if (logs.length > 1000) {
    logs.splice(0, logs.length - 1000);
  }

  await chrome.storage.local.set({ ceo_audit_log: logs });
}

// ============ MESSAGE HANDLERS ============

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'CEO_START_RECORDING':
      state.isRecording = true;
      if (state.athenaTabId && !state.debuggerAttached) {
        attachDebugger(state.athenaTabId).then(() => {
          sendResponse({ recording: true, debuggerAttached: state.debuggerAttached });
        });
        return true;
      }
      sendResponse({ recording: true });
      break;

    case 'CEO_STOP_RECORDING':
      state.isRecording = false;
      sendResponse({
        recording: false,
        stats: state.stats,
        capturedCount: state.capturedRequests.length
      });
      break;

    case 'CEO_GET_STATE':
      sendResponse({
        ...state,
        hasClaudeKey: !!CONFIG.apiKeys.claude,
        hasGeminiKey: !!CONFIG.apiKeys.gemini,
        hasCodexKey: !!CONFIG.apiKeys.openai
      });
      break;

    case 'CEO_DETECT_SESSION':
      if (message.tabId) {
        detectAthenaSession(message.tabId).then(sendResponse);
        return true;
      }
      sendResponse({ error: 'No tabId provided' });
      break;

    case 'CEO_EXECUTE_STRATEGY':
      executeExtractionStrategy(message.mrn).then(sendResponse);
      return true;

    case 'CEO_GET_ENDPOINTS':
      sendResponse(Array.from(state.discoveredEndpoints.values()));
      break;

    case 'CEO_GET_STATS':
      sendResponse(state.stats);
      break;

    case 'CEO_EXPORT_DATA':
      sendResponse({
        sessionInfo: state.sessionInfo,
        stats: state.stats,
        discoveredEndpoints: Array.from(state.discoveredEndpoints.values()),
        recentRequests: state.capturedRequests.slice(-50),
        exportedAt: new Date().toISOString()
      });
      break;

    case 'CEO_UPDATE_API_KEYS':
      if (message.keys) {
        CONFIG.apiKeys = { ...CONFIG.apiKeys, ...message.keys };
        chrome.storage.local.set({
          anthropicApiKey: message.keys.claude,
          geminiApiKey: message.keys.gemini,
          openaiApiKey: message.keys.openai
        });
      }
      sendResponse({ success: true });
      break;
  }

  return false;
});

// Handle debugger detach events
chrome.debugger.onDetach.addListener((source, reason) => {
  if (source.tabId === state.athenaTabId) {
    CEOLogger.warn('Debugger detached', { reason });
    state.debuggerAttached = false;
    broadcastMessage('DEBUGGER_STATUS', { attached: false, reason });
  }
});

// ============ INITIALIZE ============

initializeCEO();

CEOLogger.success('CEO Background Service Ready');
console.log('%c[EHR Bridge] CEO (Claude) service initialized',
  'color: #8b5cf6; font-weight: bold; font-size: 14px;');
