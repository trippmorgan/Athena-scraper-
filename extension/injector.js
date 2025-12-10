// injector.js - Content script that bridges page context and background worker
// Now handles both passive interception AND active fetch commands

(function() {
  'use strict';

  const Logger = {
    _log: (level, emoji, msg, data) => {
      const time = new Date().toLocaleTimeString('en-US', { hour12: false });
      const prefix = `[Shadow EHR Bridge ${time}]`;
      const styles = {
        info: "color: #3b82f6; font-weight: bold;",
        success: "color: #10b981; font-weight: bold;",
        warn: "color: #f59e0b; font-weight: bold;",
        error: "color: #ef4444; font-weight: bold;",
        active: "color: #f97316; font-weight: bold;"
      };
      const style = styles[level] || styles.info;
      data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
    },
    info: (msg, data) => Logger._log('info', 'ℹ️', msg, data),
    success: (msg, data) => Logger._log('success', '✅', msg, data),
    warn: (msg, data) => Logger._log('warn', '⚠️', msg, data),
    error: (msg, data) => Logger._log('error', '❌', msg, data),
    active: (msg, data) => Logger._log('active', '🎯', msg, data)
  };

  let passiveMessageCount = 0;
  let activeCommandCount = 0;
  let contextValid = true;

  // Check if extension context is still valid
  function isContextValid() {
    try {
      // This will throw if context is invalidated
      return chrome.runtime?.id != null;
    } catch (e) {
      return false;
    }
  }

  // Safe wrapper for chrome.runtime.sendMessage
  function safeSendMessage(message, callback) {
    if (!isContextValid()) {
      if (!contextValid) return; // Already logged
      contextValid = false;
      Logger.warn('Extension context invalidated - page refresh required');
      return;
    }

    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          const errorMsg = chrome.runtime.lastError.message;
          if (errorMsg.includes('context invalidated')) {
            contextValid = false;
            Logger.warn('Extension context invalidated - page refresh required');
          } else {
            Logger.error('Message send failed:', errorMsg);
          }
        } else if (callback) {
          callback(response);
        }
      });
    } catch (e) {
      if (e.message.includes('context invalidated')) {
        contextValid = false;
        Logger.warn('Extension context invalidated - page refresh required');
      } else {
        Logger.error('Send message error:', e.message);
      }
    }
  }

  Logger.info('Content script initializing...');
  Logger.info('Page:', window.location.href);

  // ============================================================
  // INJECT SCRIPTS INTO PAGE CONTEXT
  // ============================================================

  function injectScript(filename) {
    return new Promise((resolve, reject) => {
      if (!isContextValid()) {
        Logger.warn('Cannot inject script - extension context invalidated');
        reject(new Error('Extension context invalidated'));
        return;
      }

      try {
        const script = document.createElement('script');
        script.src = chrome.runtime.getURL(filename);
        script.onload = function() {
          Logger.success(`${filename} injected`);
          this.remove();
          resolve();
        };
        script.onerror = function(e) {
          Logger.error(`Failed to inject ${filename}`, e);
          reject(e);
        };
        (document.head || document.documentElement).appendChild(script);
      } catch (e) {
        if (e.message.includes('context invalidated')) {
          contextValid = false;
          Logger.warn('Extension context invalidated during injection');
        }
        reject(e);
      }
    });
  }

  // Inject both passive interceptor and active fetcher
  async function initializeInjections() {
    try {
      await injectScript('interceptor.js');  // Passive interception
      await injectScript('activeFetcher.js'); // Active fetching
      Logger.success('All scripts injected successfully');
    } catch (e) {
      Logger.error('Script injection failed', e);
    }
  }

  initializeInjections();

  // ============================================================
  // PASSIVE INTERCEPTION RELAY (existing functionality)
  // ============================================================

  window.addEventListener('message', function(event) {
    if (event.source !== window) return;

    // Handle passive interception
    if (event.data?.type === 'ATHENA_API_INTERCEPT') {
      passiveMessageCount++;
      const payload = event.data.payload;

      Logger.success(`Passive intercept #${passiveMessageCount}`, {
        method: payload.method,
        url: payload.url?.substring(0, 50) + '...'
      });

      safeSendMessage({
        type: 'API_CAPTURE',
        payload: payload
      });
    }

    // Handle active fetch results (from activeFetcher.js)
    if (event.data?.type === 'ACTIVE_FETCH_RESULT') {
      Logger.active('Active fetch result received', {
        action: event.data.action,
        success: event.data.payload?.success !== false
      });

      // Relay to background worker
      safeSendMessage({
        type: 'ACTIVE_FETCH_RESULT',
        action: event.data.action,
        payload: event.data.payload,
        callbackId: event.data.callbackId,
        timestamp: event.data.timestamp
      });
    }
  });

  // ============================================================
  // ACTIVE FETCH COMMAND RELAY (from background worker)
  // ============================================================

  // Safely register message listener
  try {
    if (isContextValid()) {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (!isContextValid()) {
          return false;
        }

        if (message.type === 'ACTIVE_FETCH_COMMAND') {
          activeCommandCount++;
          Logger.active(`Active command #${activeCommandCount}`, {
            action: message.action,
            payload: message.payload
          });

          // Forward command to page context (activeFetcher.js)
          window.postMessage({
            type: 'ACTIVE_FETCH_COMMAND',
            action: message.action,
            payload: message.payload,
            callbackId: message.callbackId
          }, '*');

          sendResponse({ forwarded: true });
        }

        return true;
      });
    }
  } catch (e) {
    Logger.warn('Failed to register message listener - extension may need refresh');
  }

  // ============================================================
  // STATUS & DIAGNOSTICS
  // ============================================================

  Logger.success('Content script ready');
  Logger.info('Modes: Passive Interception + Active Fetching');

  // Periodic status
  setInterval(() => {
    if (passiveMessageCount > 0 || activeCommandCount > 0) {
      Logger.info('Stats', {
        passiveIntercepts: passiveMessageCount,
        activeCommands: activeCommandCount
      });
    }
  }, 60000);

})();