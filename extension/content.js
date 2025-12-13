/**
 * Tier 1: The Bridge
 * Injects the hook into the DOM and forwards events to the Background Service Worker.
 *
 * This script runs in the ISOLATED world, acting as a bridge between:
 * - injected.js (Main World - can access page's JS)
 * - background.js (Service Worker - has WebSocket)
 */

const ContentLogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Shadow EHR Content ${time}]`;
    const styles = {
      info: "color: #3b82f6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      debug: "color: #8b5cf6;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => ContentLogger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => ContentLogger._log('success', '✅', msg, data),
  warn: (msg, data) => ContentLogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => ContentLogger._log('error', '❌', msg, data),
  debug: (msg, data) => ContentLogger._log('debug', '🔍', msg, data)
};

// Track statistics
let interceptCount = 0;
let lastInterceptTime = null;

// Helper to extract patient ID from URL
function extractPatientId(url) {
  if (!url) return null;
  const patterns = [
    /\/chart\/(\d+)/i,
    /chart[_-]?id[=:](\d+)/i,
    /patient[_-]?id[=:](\d+)/i,
    /\/(\d{6,10})(?:\/|$|\?)/
  ];
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

ContentLogger.info('Content script initializing...');
ContentLogger.info('Page URL: ' + window.location.href);

// 1. Inject the "Hook" script into the Main World
ContentLogger.debug('Injecting interceptor script into Main World...');

const s = document.createElement('script');
s.src = chrome.runtime.getURL('injected.js');
s.onload = function() {
  ContentLogger.success('Interceptor script injected and loaded');
  this.remove(); // Clean up the DOM tag after execution
};
s.onerror = function(e) {
  ContentLogger.error('Failed to inject interceptor script', e);
};
(document.head || document.documentElement).appendChild(s);

// 2. Listen for the Custom Event dispatched by injected.js
window.addEventListener('SHADOW_EHR_INTERCEPT', function(e) {
  const data = e.detail;
  interceptCount++;
  lastInterceptTime = new Date().toISOString();

  ContentLogger.success(`INTERCEPT EVENT #${interceptCount}`, {
    type: data.type,
    method: data.method,
    url: data.url ? (data.url.length > 60 ? data.url.substring(0, 60) + '...' : data.url) : 'N/A',
    hasPayload: !!data.payload,
    payloadType: data.payload ? typeof data.payload : 'none'
  });

  // Log payload preview
  if (data.payload && typeof data.payload === 'object') {
    const keys = Object.keys(data.payload).slice(0, 8);
    ContentLogger.debug('Payload structure:', { keys, keyCount: Object.keys(data.payload).length });
  }

  // 3. Send to Background Worker (which holds the HTTP connection)
  // IMPORTANT: background.js expects type: 'API_CAPTURE' with payload
  try {
    chrome.runtime.sendMessage({
      type: "API_CAPTURE",
      payload: {
        source: data.type || 'intercept',
        method: data.method || 'GET',
        url: data.url,
        data: data.payload,
        patientId: extractPatientId(data.url),
        timestamp: data.timestamp || new Date().toISOString(),
        size: data.payload ? JSON.stringify(data.payload).length : 0
      }
    }, (response) => {
      if (chrome.runtime.lastError) {
        ContentLogger.error('Failed to send to background:', chrome.runtime.lastError.message);
      } else {
        ContentLogger.debug('Message sent to background worker', response);
      }
    });
  } catch (err) {
    ContentLogger.error('Exception sending message:', err);
  }
});

// Log ready status
ContentLogger.success('Content script ready and listening for intercepts');
ContentLogger.info('Waiting for API calls from AthenaNet...');

// Periodic status log
setInterval(() => {
  if (interceptCount > 0) {
    ContentLogger.info(`Status: ${interceptCount} intercepts captured`, {
      lastIntercept: lastInterceptTime
    });
  }
}, 60000); // Every minute
