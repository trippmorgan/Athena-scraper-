// background.js - Service worker with Active Fetch support
// Handles both passive interception relay AND active fetch commands

const LOCAL_SERVICE_URL = 'http://localhost:8000';

// State tracking
let connectionStatus = 'disconnected';
let captureCount = 0;
let activeFetchCount = 0;
let lastError = null;
let bytesSent = 0;

// Queue for offline buffering
let pendingQueue = [];
const MAX_QUEUE_SIZE = 100;

// Track tabs with active Athena sessions
const athenaTabs = new Map();

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

// Update badge based on status
function updateBadge(mode = 'passive') {
  if (chrome.action) {
    if (connectionStatus === 'connected') {
      if (mode === 'active') {
        chrome.action.setBadgeText({ text: 'ACT' });
        chrome.action.setBadgeBackgroundColor({ color: '#f97316' }); // Orange for active
      } else {
        chrome.action.setBadgeText({ text: 'ON' });
        chrome.action.setBadgeBackgroundColor({ color: '#10b981' });
      }
    } else if (connectionStatus === 'error') {
      chrome.action.setBadgeText({ text: 'ERR' });
      chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });
    } else {
      chrome.action.setBadgeText({ text: 'OFF' });
      chrome.action.setBadgeBackgroundColor({ color: '#6b7280' });
    }
  }
}

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
        'X-Source': 'athena-bridge'
      },
      body: payloadJson
    });

    if (response.ok) {
      const oldStatus = connectionStatus;
      connectionStatus = 'connected';
      captureCount++;
      bytesSent += payloadSize;
      lastError = null;

      if (oldStatus !== 'connected') {
        updateBadge();
      }

      // Process queued items
      while (pendingQueue.length > 0) {
        const queued = pendingQueue.shift();
        try {
          await fetch(`${LOCAL_SERVICE_URL}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(queued)
          });
        } catch (e) {
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

    if (pendingQueue.length < MAX_QUEUE_SIZE) {
      pendingQueue.push(payload);
    }

    return false;
  }
}

// ============================================================
// ACTIVE FETCH - Send commands to content script
// ============================================================

async function sendActiveFetchCommand(tabId, action, payload) {
  Logger.active('ACTIVE FETCH COMMAND', { tabId, action, payload });
  activeFetchCount++;
  updateBadge('active');

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Active fetch timeout'));
    }, 30000); // 30 second timeout

    // Store callback for response
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
    });
  });
}

const activeFetchCallbacks = new Map();

// Find an active Athena tab
function findAthenaTab() {
  for (const [tabId, info] of athenaTabs) {
    if (info.active) return tabId;
  }
  return null;
}

// ============================================================
// MESSAGE HANDLERS
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id || 'unknown';

  // Track Athena tabs
  if (sender.tab?.url?.includes('athenahealth.com')) {
    athenaTabs.set(tabId, { active: true, url: sender.tab.url });
  }

  // Handle passive interception (existing)
  if (message.type === 'API_CAPTURE') {
    Logger.data('PASSIVE CAPTURE', {
      source: message.payload?.source,
      method: message.payload?.method,
      url: message.payload?.url?.substring(0, 50) + '...'
    });

    sendToLocalService(message.payload);
    sendResponse({ received: true, queued: connectionStatus !== 'connected' });
  }

  // Handle active fetch results from content script
  if (message.type === 'ACTIVE_FETCH_RESULT') {
    Logger.active('ACTIVE FETCH RESULT', {
      action: message.action,
      success: message.payload?.success !== false,
      callbackId: message.callbackId
    });

    const callback = activeFetchCallbacks.get(message.callbackId);
    if (callback) {
      clearTimeout(callback.timeout);
      activeFetchCallbacks.delete(message.callbackId);
      callback.resolve(message.payload);
    }

    // Also forward to backend
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

  // Handle requests from frontend to initiate active fetch
  if (message.type === 'INITIATE_ACTIVE_FETCH') {
    const athenaTabId = findAthenaTab();
    
    if (!athenaTabId) {
      Logger.error('No active Athena tab found');
      sendResponse({ error: 'No active Athena session. Please open AthenaNet.' });
      return true;
    }

    sendActiveFetchCommand(athenaTabId, message.action, message.payload)
      .then(result => {
        sendResponse({ success: true, data: result });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });

    return true; // Keep channel open for async response
  }

  // Status request
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

  return true;
});

// Track tab closures
chrome.tabs.onRemoved.addListener((tabId) => {
  if (athenaTabs.has(tabId)) {
    athenaTabs.delete(tabId);
    Logger.info(`Athena tab ${tabId} closed`);
  }
});

// ============================================================
// EXTERNAL MESSAGE HANDLER (from frontend WebSocket)
// ============================================================

// Listen for messages from the frontend via native messaging or fetch
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

// Health check ping
setInterval(async () => {
  try {
    const res = await fetch(`${LOCAL_SERVICE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)
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
}, 10000);

// Initial health check
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