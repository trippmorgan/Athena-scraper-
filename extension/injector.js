// injector.js - Content script that injects interceptor into page context
// This runs in the content script context and bridges to the page's JS context

(function() {
  'use strict';

  const Logger = {
    _log: (level, emoji, msg, data) => {
      const time = new Date().toLocaleTimeString('en-US', { hour12: false });
      const prefix = `[AthenaNet Bridge Injector ${time}]`;
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
    info: (msg, data) => Logger._log('info', 'ℹ️', msg, data),
    success: (msg, data) => Logger._log('success', '✅', msg, data),
    warn: (msg, data) => Logger._log('warn', '⚠️', msg, data),
    error: (msg, data) => Logger._log('error', '❌', msg, data),
    debug: (msg, data) => Logger._log('debug', '🔍', msg, data)
  };

  let messageCount = 0;

  Logger.info('Injector initializing...');
  Logger.info('Page:', window.location.href);

  // Inject the interceptor script into the page's actual context
  // (content scripts can't access window.fetch directly - isolation)
  const script = document.createElement('script');
  script.src = chrome.runtime.getURL('interceptor.js');
  script.onload = function() {
    Logger.success('Interceptor script injected successfully');
    this.remove(); // Clean up after injection
  };
  script.onerror = function(e) {
    Logger.error('Failed to inject interceptor script', e);
  };
  (document.head || document.documentElement).appendChild(script);

  // Listen for messages from the injected script (via window.postMessage)
  window.addEventListener('message', function(event) {
    // Security: only accept messages from same window
    if (event.source !== window) return;
    if (!event.data || event.data.type !== 'ATHENA_API_INTERCEPT') return;

    messageCount++;
    const payload = event.data.payload;

    Logger.success(`Message #${messageCount} received from interceptor`, {
      source: payload.source,
      method: payload.method,
      url: payload.url?.substring(0, 50) + '...',
      patientId: payload.patientId,
      size: payload.size
    });

    // Forward to background service worker
    try {
      chrome.runtime.sendMessage({
        type: 'API_CAPTURE',
        payload: payload
      }, (response) => {
        if (chrome.runtime.lastError) {
          Logger.error('Failed to send to background:', chrome.runtime.lastError.message);
        } else {
          Logger.debug('Forwarded to background worker');
        }
      });
    } catch (err) {
      Logger.error('Exception forwarding message:', err);
    }
  });

  Logger.success('Injector ready and listening');

  // Periodic stats
  setInterval(() => {
    if (messageCount > 0) {
      Logger.info(`Stats: ${messageCount} messages forwarded`);
    }
  }, 60000);

})();
