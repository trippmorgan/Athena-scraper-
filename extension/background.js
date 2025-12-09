// background.js - Service worker that forwards data to local Python service

const LOCAL_SERVICE_URL = 'http://localhost:8000';

// State tracking
let connectionStatus = 'disconnected';
let captureCount = 0;
let lastError = null;
let bytesSent = 0;

// Queue for offline buffering
let pendingQueue = [];
const MAX_QUEUE_SIZE = 100;

// Logger utility
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
      data: "color: #22c55e; font-weight: bold;"
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
  separator: () => console.log('%c' + '═'.repeat(60), 'color: #475569;')
};

Logger.separator();
Logger.info('Background service worker starting...');
Logger.info('Target service:', LOCAL_SERVICE_URL);
Logger.separator();

// Update badge based on status
function updateBadge() {
  if (chrome.action) {
    if (connectionStatus === 'connected') {
      chrome.action.setBadgeText({ text: 'ON' });
      chrome.action.setBadgeBackgroundColor({ color: '#10b981' });
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

  Logger.separator();
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

      Logger.success('PAYLOAD DELIVERED', {
        totalCaptures: captureCount,
        totalBytes: `${(bytesSent / 1024).toFixed(2)} KB`,
        queueSize: pendingQueue.length
      });

      if (oldStatus !== 'connected') {
        updateBadge();
      }

      // Process any queued items
      while (pendingQueue.length > 0) {
        const queued = pendingQueue.shift();
        Logger.info(`Processing queued item (${pendingQueue.length} remaining)`);
        try {
          await fetch(`${LOCAL_SERVICE_URL}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(queued)
          });
        } catch (e) {
          Logger.warn('Failed to send queued item, re-queuing');
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

    Logger.error('DELIVERY FAILED', {
      error: error.message,
      queueSize: pendingQueue.length
    });

    // Queue for retry (if not full)
    if (pendingQueue.length < MAX_QUEUE_SIZE) {
      pendingQueue.push(payload);
      Logger.info(`Queued for retry (${pendingQueue.length}/${MAX_QUEUE_SIZE})`);
    } else {
      Logger.warn('Queue full, dropping payload');
    }

    return false;
  }
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id || 'unknown';

  Logger.debug(`Message from tab ${tabId}:`, { type: message.type });

  if (message.type === 'API_CAPTURE') {
    Logger.separator();
    Logger.data('CAPTURE RECEIVED', {
      source: message.payload?.source,
      method: message.payload?.method,
      url: message.payload?.url?.substring(0, 50) + '...',
      patientId: message.payload?.patientId
    });

    sendToLocalService(message.payload);
    sendResponse({ received: true, queued: connectionStatus !== 'connected' });
  }

  if (message.type === 'GET_STATUS') {
    const status = {
      connectionStatus,
      captureCount,
      bytesSent,
      queueSize: pendingQueue.length,
      lastError
    };
    Logger.info('Status requested:', status);
    sendResponse(status);
  }

  return true; // Keep channel open for async
});

// Health check ping every 10 seconds
setInterval(async () => {
  try {
    const res = await fetch(`${LOCAL_SERVICE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    });

    const oldStatus = connectionStatus;
    connectionStatus = res.ok ? 'connected' : 'error';

    if (oldStatus !== connectionStatus) {
      Logger.info(`Connection status: ${oldStatus} -> ${connectionStatus}`);
      updateBadge();
    }
  } catch (e) {
    if (connectionStatus !== 'disconnected') {
      Logger.warn('Backend unreachable');
      connectionStatus = 'disconnected';
      updateBadge();
    }
  }
}, 10000);

// Initial health check
setTimeout(async () => {
  Logger.info('Performing initial health check...');
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

Logger.success('Background service worker ready');
