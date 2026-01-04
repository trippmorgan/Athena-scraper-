/**
 * =============================================================================
 * BACKGROUND.JS - The Data Relay Service Worker
 * =============================================================================
 *
 * ARCHITECTURAL ROLE:
 * This is the third component in the data flow pipeline. It runs as a
 * Chrome extension service worker (Manifest V3) and is responsible for
 * reliably transmitting captured data to the Python backend.
 *
 * DATA FLOW POSITION: [3/7]
 *   interceptor.js -> injector.js -> [background.js] -> main.py ->
 *   fhir_converter.py -> WebSocket -> SurgicalDashboard.tsx
 *
 * CRITICAL RESPONSIBILITIES:
 *
 * 1. DATA RELAY (Primary)
 *    Receives API_CAPTURE messages from content scripts and forwards
 *    to backend via HTTP POST /ingest. This is the MOST IMPORTANT function.
 *
 * 2. CONNECTION MANAGEMENT
 *    Maintains connection status with backend via health checks.
 *    Updates badge to show ON/OFF/ERR status.
 *
 * 3. OFFLINE QUEUE
 *    If backend is unavailable, queues messages for later delivery.
 *    Prevents data loss during backend restarts.
 *
 * 4. ACTIVE FETCH COORDINATION
 *    Routes active fetch commands from popup/frontend to content scripts.
 *    Manages callbacks for async active fetch results.
 *
 * 5. TAB TRACKING
 *    Tracks which tabs have active Athena sessions for targeting
 *    active fetch commands to the correct tab.
 *
 * SERVICE WORKER LIFECYCLE:
 * In Manifest V3, background scripts are service workers that can be
 * terminated after inactivity. State must be recoverable, and we use
 * the health check interval to keep the worker alive during active use.
 *
 * DESIGN PRINCIPLE:
 * The data relay function MUST be non-blocking and always first.
 * Any AI processing or enhancement happens AFTER successful relay.
 * The system MUST work even if AI features fail.
 *
 * =============================================================================
 */

const LOCAL_SERVICE_URL = 'http://localhost:8000';
const OBSERVER_URL = 'http://localhost:3000';

// =============================================================================
// AUTO-FETCH CONFIGURATION
// =============================================================================
// Set to true to automatically fetch clinical data when a new patient is detected
// This is OPT-IN by default to avoid unexpected behavior
const AUTO_FETCH_ENABLED = true;  // ENABLED - auto-fetch on patient detection
const AUTO_FETCH_DEBOUNCE_MS = 30000;  // Don't auto-fetch same patient within 30 seconds
let lastAutoFetchPatient = null;
let lastAutoFetchTime = 0;

// =============================================================================
// OBSERVER TELEMETRY
// =============================================================================
/**
 * emitTelemetry(action, success, data)
 * ------------------------------------
 * Sends telemetry events to Medical Mirror Observer for pipeline monitoring.
 * This is NON-BLOCKING and fails silently - Observer is optional.
 *
 * @param {string} action - The action being performed (init, relay, error, etc.)
 * @param {boolean} success - Whether the action succeeded
 * @param {object} data - Additional context data
 */
async function emitTelemetry(action, success, data = {}) {
  try {
    await fetch(`${OBSERVER_URL}/api/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'OBSERVER_TELEMETRY',
        source: 'athena-scraper',
        event: {
          stage: 'background',
          action: action,
          success: success,
          timestamp: new Date().toISOString(),
          data: data
        }
      })
    });
  } catch (e) {
    // Silent fail - Observer is optional, don't break main flow
  }
}

// =============================================================================
// STATE MANAGEMENT
// =============================================================================
/**
 * Connection and statistics state.
 * These values are lost if service worker restarts, but are non-critical.
 */
let connectionStatus = 'disconnected';  // 'connected' | 'disconnected' | 'error'
let captureCount = 0;                   // Total passive captures
let activeFetchCount = 0;               // Total active fetch commands
let lastError = null;                   // Most recent error message
let bytesSent = 0;                      // Total bytes sent to backend

/**
 * OFFLINE QUEUE
 * -------------
 * If backend is unavailable, captured data is queued here.
 * When backend comes online, queue is processed.
 * Limited to MAX_QUEUE_SIZE to prevent memory issues.
 */
let pendingQueue = [];
const MAX_QUEUE_SIZE = 100;

/**
 * ATHENA TAB TRACKING
 * -------------------
 * Maps tab IDs to Athena session info.
 * Used to route active fetch commands to correct tab.
 */
const athenaTabs = new Map();

/**
 * ACTIVE FETCH CALLBACKS
 * ----------------------
 * Maps callback IDs to Promise resolvers.
 * Active fetch is async: we send command, then wait for result message.
 */
const activeFetchCallbacks = new Map();

// =============================================================================
// LOGGING UTILITY
// =============================================================================
/**
 * Styled console output for service worker.
 * Note: Service worker console is separate from page console.
 * View in: chrome://extensions -> service worker "Inspect"
 */
const Logger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[AthenaNet Bridge ${time}]`;
    const styles = {
      info: "color: #3b82f6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      debug: "color: #8b5cf6;",
      data: "color: #22c55e; font-weight: bold;",
      active: "color: #f97316; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => Logger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => Logger._log('success', '✅', msg, data),
  warn: (msg, data) => Logger._log('warn', '⚠️', msg, data),
  error: (msg, data) => Logger._log('error', '❌', msg, data),
  debug: (msg, data) => Logger._log('debug', '🔍', msg, data),
  data: (msg, data) => Logger._log('data', '📦', msg, data),
  active: (msg, data) => Logger._log('active', '🎯', msg, data),
  separator: () => console.log('%c' + '═'.repeat(60), 'color: #475569;')
};

Logger.separator();
Logger.info('Background service worker starting...');
Logger.info('Target service:', LOCAL_SERVICE_URL);
Logger.separator();

// Emit init telemetry
emitTelemetry('init', true, { target: LOCAL_SERVICE_URL });

// =============================================================================
// BADGE MANAGEMENT
// =============================================================================
/**
 * updateBadge(mode)
 * -----------------
 * Updates the extension toolbar badge to show current status.
 *
 * Badge States:
 * - "ON" (green): Connected to backend, passive mode
 * - "ACT" (orange): Connected, active fetch in progress
 * - "ERR" (red): Connection error
 * - "OFF" (gray): Disconnected from backend
 *
 * @param {string} mode - 'passive' or 'active'
 */
function updateBadge(mode = 'passive') {
  if (chrome.action) {
    if (connectionStatus === 'connected') {
      if (mode === 'active') {
        chrome.action.setBadgeText({ text: 'ACT' });
        chrome.action.setBadgeBackgroundColor({ color: '#f97316' }); // Orange
      } else {
        chrome.action.setBadgeText({ text: 'ON' });
        chrome.action.setBadgeBackgroundColor({ color: '#10b981' }); // Green
      }
    } else if (connectionStatus === 'error') {
      chrome.action.setBadgeText({ text: 'ERR' });
      chrome.action.setBadgeBackgroundColor({ color: '#ef4444' }); // Red
    } else {
      chrome.action.setBadgeText({ text: 'OFF' });
      chrome.action.setBadgeBackgroundColor({ color: '#6b7280' }); // Gray
    }
  }
}

// =============================================================================
// CORE DATA RELAY
// =============================================================================
/**
 * sendToLocalService(payload)
 * ---------------------------
 * THE MOST CRITICAL FUNCTION IN THIS FILE.
 *
 * Sends captured data to the Python backend via HTTP POST.
 * This is the primary data pipeline - it MUST be reliable.
 *
 * Features:
 * 1. Sends payload to /ingest endpoint
 * 2. Updates connection status based on response
 * 3. Processes offline queue when connection restored
 * 4. Queues failed requests for retry
 *
 * Error Handling:
 * - Network errors: Queue payload, mark status as error
 * - HTTP errors: Log and continue
 * - Never throw - relay must not break
 *
 * @param {object} payload - Captured API data to send
 * @returns {Promise<boolean>} - True if sent successfully
 */
async function sendToLocalService(payload) {
  const payloadJson = JSON.stringify(payload);
  const payloadSize = new TextEncoder().encode(payloadJson).length;

  Logger.data('SENDING TO BACKEND', {
    url: payload.url?.substring(0, 60) + '...',
    method: payload.method,
    patientId: payload.patientId,
    size: `${(payloadSize / 1024).toFixed(2)} KB`
  });

  try {
    const response = await fetch(`${LOCAL_SERVICE_URL}/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Source': 'athena-bridge'  // Identifies traffic source in backend
      },
      body: payloadJson
    });

    if (response.ok) {
      const oldStatus = connectionStatus;
      connectionStatus = 'connected';
      captureCount++;
      bytesSent += payloadSize;
      lastError = null;

      // Emit telemetry for successful relay
      emitTelemetry('relay', true, {
        url: payload.url?.substring(0, 60),
        method: payload.method,
        patientId: payload.patientId,
        size: payloadSize
      });

      // Update badge if status changed
      if (oldStatus !== 'connected') {
        updateBadge();
      }

      // QUEUE DRAIN: Process any queued items now that we're connected
      while (pendingQueue.length > 0) {
        const queued = pendingQueue.shift();
        try {
          await fetch(`${LOCAL_SERVICE_URL}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(queued)
          });
        } catch (e) {
          // If queue drain fails, put item back and stop
          pendingQueue.unshift(queued);
          break;
        }
      }

      return true;
    } else {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
  } catch (error) {
    connectionStatus = 'error';
    lastError = error.message;
    updateBadge();

    // Emit telemetry for failed relay
    emitTelemetry('relay', false, {
      url: payload.url?.substring(0, 60),
      error: error.message,
      queued: pendingQueue.length < MAX_QUEUE_SIZE
    });

    // QUEUE FOR RETRY: Don't lose data if backend is down
    if (pendingQueue.length < MAX_QUEUE_SIZE) {
      pendingQueue.push(payload);
      Logger.warn(`Queued for retry (queue size: ${pendingQueue.length})`);
    } else {
      Logger.error('Queue full, dropping payload');
    }

    return false;
  }
}

// =============================================================================
// ACTIVE FETCH SYSTEM
// =============================================================================
/**
 * sendActiveFetchCommand(tabId, action, payload)
 * -----------------------------------------------
 * Sends an active fetch command to a specific Athena tab.
 *
 * Active Fetch vs Passive Capture:
 * - Passive: We observe requests Athena makes on its own
 * - Active: We initiate requests for specific data (e.g., by MRN)
 *
 * How It Works:
 * 1. Generate unique callback ID
 * 2. Store Promise resolver in activeFetchCallbacks map
 * 3. Send command to content script via chrome.tabs.sendMessage
 * 4. Content script forwards to activeFetcher.js in page context
 * 5. activeFetcher.js makes request and posts result back
 * 6. Result message triggers callback resolution
 *
 * Timeout: 30 seconds (EHR systems can be slow)
 *
 * @param {number} tabId - Chrome tab ID with Athena session
 * @param {string} action - Fetch action (FETCH_PREOP, etc.)
 * @param {object} payload - Action parameters (MRN, etc.)
 * @returns {Promise} - Resolves with fetch result
 */
async function sendActiveFetchCommand(tabId, action, payload) {
  Logger.active('ACTIVE FETCH COMMAND', { tabId, action, payload });
  activeFetchCount++;
  updateBadge('active');

  // Emit telemetry for active fetch initiation
  emitTelemetry('active-fetch', true, { action, tabId });

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Active fetch timeout'));
    }, 30000); // 30 second timeout

    // Generate unique callback ID
    const callbackId = `${action}_${Date.now()}`;
    activeFetchCallbacks.set(callbackId, { resolve, reject, timeout });

    // Send command to content script
    chrome.tabs.sendMessage(tabId, {
      type: 'ACTIVE_FETCH_COMMAND',
      action,
      payload,
      callbackId
    }, (response) => {
      if (chrome.runtime.lastError) {
        clearTimeout(timeout);
        activeFetchCallbacks.delete(callbackId);
        reject(new Error(chrome.runtime.lastError.message));
      }
      // Success: wait for result via ACTIVE_FETCH_RESULT message
    });
  });
}

/**
 * findAthenaTab()
 * ---------------
 * Finds a tab with an active Athena session.
 *
 * Used for active fetch commands - we need to know which tab
 * to send the command to.
 *
 * @returns {number|null} - Tab ID or null if none found
 */
function findAthenaTab() {
  for (const [tabId, info] of athenaTabs) {
    if (info.active) return tabId;
  }
  return null;
}

// =============================================================================
// MESSAGE HANDLERS
// =============================================================================
/**
 * Runtime Message Listener
 * ------------------------
 * Handles all incoming messages from content scripts and popup.
 *
 * Message Types:
 *
 * API_CAPTURE
 * - Source: injector.js (content script)
 * - Contains: Captured API response data
 * - Action: Forward to backend via sendToLocalService()
 *
 * ACTIVE_FETCH_RESULT
 * - Source: injector.js relaying from activeFetcher.js
 * - Contains: Result of active fetch command
 * - Action: Resolve pending callback, send to backend
 *
 * INITIATE_ACTIVE_FETCH
 * - Source: popup.js or external frontend
 * - Contains: Action and payload for active fetch
 * - Action: Route to appropriate Athena tab
 *
 * GET_STATUS
 * - Source: popup.js
 * - Action: Return current status for display
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id || 'unknown';

  // TRACK ATHENA TABS
  // Any message from an Athena tab registers that tab
  if (sender.tab?.url?.includes('athenahealth.com')) {
    athenaTabs.set(tabId, { active: true, url: sender.tab.url });
  }

  // PASSIVE CAPTURE RELAY (Primary data flow)
  if (message.type === 'API_CAPTURE') {
    Logger.data('PASSIVE CAPTURE', {
      source: message.payload?.source,
      method: message.payload?.method,
      url: message.payload?.url?.substring(0, 50) + '...'
    });

    // CRITICAL: Send to backend immediately
    sendToLocalService(message.payload);
    sendResponse({ received: true, queued: connectionStatus !== 'connected' });
  }

  // PATIENT DETECTED - Auto-Fetch Trigger
  // When interceptor detects a new patient, optionally trigger active fetch
  if (message.type === 'PATIENT_DETECTED') {
    const patientId = message.patientId;
    const now = Date.now();

    Logger.info(`🆕 PATIENT DETECTED: ${patientId}`);
    emitTelemetry('patient-detected', true, { patientId, source: message.source });

    // Check if auto-fetch is enabled and debounce
    if (AUTO_FETCH_ENABLED) {
      const shouldFetch = (patientId !== lastAutoFetchPatient) ||
                          (now - lastAutoFetchTime > AUTO_FETCH_DEBOUNCE_MS);

      if (shouldFetch) {
        lastAutoFetchPatient = patientId;
        lastAutoFetchTime = now;

        Logger.active(`🚀 AUTO-FETCH triggered for patient ${patientId}`);
        emitTelemetry('auto-fetch-trigger', true, { patientId });

        // Find Athena tab and trigger fetch
        const athenaTabId = findAthenaTab();
        if (athenaTabId) {
          // Fetch pre-op data (demographics, problems, medications, allergies)
          sendActiveFetchCommand(athenaTabId, 'FETCH_PREOP', { patientId })
            .then(result => {
              Logger.success(`✅ AUTO-FETCH complete for ${patientId}`);
              emitTelemetry('auto-fetch-complete', true, { patientId });
            })
            .catch(error => {
              Logger.error(`❌ AUTO-FETCH failed: ${error.message}`);
              emitTelemetry('auto-fetch-complete', false, { patientId, error: error.message });
            });
        } else {
          Logger.warn('No Athena tab found for auto-fetch');
        }
      } else {
        Logger.debug(`Auto-fetch skipped (debounce) for ${patientId}`);
      }
    } else {
      Logger.debug(`Auto-fetch disabled - patient ${patientId} detected but not fetching`);
    }

    sendResponse({ received: true, autoFetchEnabled: AUTO_FETCH_ENABLED });
  }

  // ACTIVE FETCH RESULT (from content script)
  if (message.type === 'ACTIVE_FETCH_RESULT') {
    Logger.active('ACTIVE FETCH RESULT', {
      action: message.action,
      success: message.payload?.success !== false,
      callbackId: message.callbackId
    });

    // Resolve pending callback
    const callback = activeFetchCallbacks.get(message.callbackId);
    if (callback) {
      clearTimeout(callback.timeout);
      activeFetchCallbacks.delete(message.callbackId);
      callback.resolve(message.payload);
    }

    // Also forward to backend for processing
    sendToLocalService({
      url: `active-fetch/${message.action}`,
      method: 'ACTIVE',
      data: message.payload,
      source: 'active-fetch',
      timestamp: new Date().toISOString(),
      size: JSON.stringify(message.payload).length
    });

    sendResponse({ received: true });
    updateBadge('passive'); // Reset badge
  }

  // INITIATE ACTIVE FETCH (from popup/frontend)
  if (message.type === 'INITIATE_ACTIVE_FETCH') {
    const athenaTabId = findAthenaTab();

    if (!athenaTabId) {
      Logger.error('No active Athena tab found');
      sendResponse({ error: 'No active Athena session. Please open AthenaNet.' });
      return true;
    }

    // Async: send command and wait for result
    sendActiveFetchCommand(athenaTabId, message.action, message.payload)
      .then(result => {
        sendResponse({ success: true, data: result });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });

    return true; // Keep message channel open for async response
  }

  // STATUS REQUEST (from popup)
  if (message.type === 'GET_STATUS') {
    const status = {
      connectionStatus,
      captureCount,
      activeFetchCount,
      bytesSent,
      queueSize: pendingQueue.length,
      lastError,
      athenaTabs: Array.from(athenaTabs.keys())
    };
    sendResponse(status);
  }

  return true; // Keep message channel open
});

// =============================================================================
// TAB LIFECYCLE TRACKING
// =============================================================================
/**
 * Track tab closures to clean up Athena tab registry.
 * Prevents stale tab references in athenaTabs map.
 */
chrome.tabs.onRemoved.addListener((tabId) => {
  if (athenaTabs.has(tabId)) {
    athenaTabs.delete(tabId);
    Logger.info(`Athena tab ${tabId} closed`);
  }
});

// =============================================================================
// EXTERNAL MESSAGE HANDLER
// =============================================================================
/**
 * External Message Listener
 * -------------------------
 * Handles messages from external sources (e.g., frontend app).
 *
 * Enabled via manifest.json externally_connectable.
 * Allows localhost apps to trigger active fetch without popup.
 */
chrome.runtime.onMessageExternal?.addListener((message, sender, sendResponse) => {
  Logger.info('External message received:', message);

  if (message.type === 'ACTIVE_FETCH') {
    const athenaTabId = findAthenaTab();
    if (athenaTabId) {
      sendActiveFetchCommand(athenaTabId, message.action, message.payload)
        .then(sendResponse)
        .catch(e => sendResponse({ error: e.message }));
      return true;
    }
    sendResponse({ error: 'No Athena tab' });
  }
});

// =============================================================================
// HEALTH CHECK SYSTEM
// =============================================================================
/**
 * Periodic Health Check
 * ---------------------
 * Pings backend /health endpoint every 10 seconds.
 *
 * Purposes:
 * 1. Detect when backend comes online/offline
 * 2. Update badge status
 * 3. Keep service worker alive during active use
 *
 * Uses AbortSignal.timeout for 5-second timeout to prevent hanging.
 */
setInterval(async () => {
  try {
    const res = await fetch(`${LOCAL_SERVICE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)  // 5 second timeout
    });

    const oldStatus = connectionStatus;
    connectionStatus = res.ok ? 'connected' : 'error';

    if (oldStatus !== connectionStatus) {
      Logger.info(`Connection: ${oldStatus} -> ${connectionStatus}`);
      updateBadge();
    }
  } catch (e) {
    if (connectionStatus !== 'disconnected') {
      connectionStatus = 'disconnected';
      updateBadge();
    }
  }
}, 10000); // Every 10 seconds

// =============================================================================
// INITIALIZATION
// =============================================================================
/**
 * Initial Health Check
 * --------------------
 * Check backend availability at startup.
 * Delayed 1 second to allow service worker to fully initialize.
 */
setTimeout(async () => {
  Logger.info('Initial health check...');
  try {
    const res = await fetch(`${LOCAL_SERVICE_URL}/health`);
    connectionStatus = res.ok ? 'connected' : 'disconnected';
    Logger.success(`Initial status: ${connectionStatus}`);
  } catch {
    connectionStatus = 'disconnected';
    Logger.warn('Backend not available at startup');
  }
  updateBadge();
}, 1000);

Logger.success('Background service worker ready (Passive + Active modes)');
