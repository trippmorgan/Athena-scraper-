/**
 * =============================================================================
 * INJECTOR.JS - The Context Bridge
 * =============================================================================
 *
 * ARCHITECTURAL ROLE:
 * This is the second component in the data flow pipeline. It runs as a
 * Chrome extension content script and bridges two isolated JavaScript contexts:
 *   1. Page Context (MAIN world) - where interceptor.js runs
 *   2. Extension Context (ISOLATED world) - where background.js runs
 *
 * DATA FLOW POSITION: [2/7]
 *   interceptor.js -> [injector.js] -> background.js -> main.py ->
 *   fhir_converter.py -> WebSocket -> SurgicalDashboard.tsx
 *
 * WHY THIS EXISTS:
 *
 * Chrome Extension Security Model:
 * --------------------------------
 * Chrome enforces strict isolation between page scripts and extension code.
 * - Page scripts (interceptor.js) can access window.fetch, DOM, etc.
 * - Extension code (background.js) can access chrome.* APIs
 * - Neither can directly call the other
 *
 * Content scripts are the ONLY code that can communicate with both worlds:
 * - They can inject scripts into the page context
 * - They can use chrome.runtime.sendMessage to talk to background
 * - They can listen to window.postMessage from page context
 *
 * COMMUNICATION CHANNELS:
 *
 * 1. Page -> Content Script (Passive Capture)
 *    interceptor.js -> window.postMessage({ type: 'ATHENA_API_INTERCEPT' })
 *    injector.js listens and forwards via chrome.runtime.sendMessage
 *
 * 2. Content Script -> Background (Data Relay)
 *    injector.js -> chrome.runtime.sendMessage({ type: 'API_CAPTURE' })
 *    background.js receives and sends to backend
 *
 * 3. Background -> Content Script (Active Fetch Commands)
 *    background.js -> chrome.tabs.sendMessage({ type: 'ACTIVE_FETCH_COMMAND' })
 *    injector.js -> window.postMessage to activeFetcher.js in page context
 *
 * CONTEXT INVALIDATION:
 * When the extension is reloaded or updated, existing content scripts become
 * "orphaned" - their chrome.* APIs stop working. This is handled by checking
 * chrome.runtime.id before each API call and gracefully degrading.
 *
 * =============================================================================
 */

(function() {
  'use strict';

  /**
   * LOGGING UTILITY
   * ---------------
   * Styled console output for the content script context.
   * Uses different colors than interceptor.js to distinguish in console.
   */
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

  /**
   * STATISTICS
   * ----------
   * Counters for monitoring bridge activity.
   */
  let passiveMessageCount = 0;  // Messages from interceptor.js
  let activeCommandCount = 0;   // Commands from background.js
  let contextValid = true;      // Extension context validity flag

  // ============ OBSERVER TELEMETRY ============
  function emitTelemetry(action, success, data = {}) {
    try {
      window.postMessage({
        type: 'OBSERVER_TELEMETRY',
        source: 'athena-scraper',
        event: {
          stage: 'injector',
          action: action,
          success: success,
          timestamp: new Date().toISOString(),
          data: data
        }
      }, '*');
    } catch (e) {
      // Silent fail - observer is optional
    }
  }

  /**
   * isContextValid()
   * ----------------
   * Checks if the extension context is still valid.
   *
   * When Does Context Become Invalid?
   * - Extension is reloaded (developer mode refresh)
   * - Extension is updated
   * - Extension is disabled
   *
   * Why Check?
   * Calling chrome.* APIs with an invalid context throws an error
   * that can break the page. We check first to fail gracefully.
   *
   * @returns {boolean} - True if chrome APIs are available
   */
  function isContextValid() {
    try {
      // This will throw if context is invalidated
      return chrome.runtime?.id != null;
    } catch (e) {
      return false;
    }
  }

  /**
   * safeSendMessage(message, callback)
   * ----------------------------------
   * Wraps chrome.runtime.sendMessage with context validation and error handling.
   *
   * Handles:
   * 1. Context invalidation (extension reloaded)
   * 2. Communication errors (background script not ready)
   * 3. Callback management for async responses
   *
   * @param {object} message - Message to send to background script
   * @param {function} callback - Optional callback for response
   */
  function safeSendMessage(message, callback) {
    if (!isContextValid()) {
      if (!contextValid) return; // Already logged once
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

  // ============================================================================
  // SCRIPT INJECTION
  // ============================================================================
  /**
   * injectScript(filename)
   * ----------------------
   * Injects a script file into the page context (MAIN world).
   *
   * How It Works:
   * 1. Create a <script> element
   * 2. Set src to the extension's web-accessible resource URL
   * 3. Append to document.head
   * 4. Script executes in page context, gaining access to window.fetch
   * 5. Remove script tag after load (cleanup)
   *
   * Why Inject?
   * Content scripts run in an isolated world with their own globals.
   * To hook window.fetch on the actual page, we need code in MAIN world.
   * manifest.json's web_accessible_resources allows this injection.
   *
   * @param {string} filename - Script filename in extension folder
   * @returns {Promise} - Resolves when script loads
   */
  function injectScript(filename) {
    return new Promise((resolve, reject) => {
      if (!isContextValid()) {
        Logger.warn('Cannot inject script - extension context invalidated');
        reject(new Error('Extension context invalidated'));
        return;
      }

      try {
        const script = document.createElement('script');
        // chrome.runtime.getURL gives the full extension:// URL
        script.src = chrome.runtime.getURL(filename);
        script.onload = function() {
          Logger.success(`${filename} injected`);
          this.remove(); // Cleanup DOM
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

  /**
   * initializeInjections()
   * ----------------------
   * Injects all required scripts into the page context.
   *
   * Order Matters:
   * 1. interceptor.js - Sets up fetch/XHR hooks for passive capture
   * 2. activeFetcher.js - Enables on-demand data fetching
   *
   * Both scripts run in page context and communicate back via postMessage.
   */
  async function initializeInjections() {
    try {
      await injectScript('interceptor.js');  // Passive interception
      await injectScript('activeFetcher.js'); // Active fetching
      Logger.success('All scripts injected successfully');
    } catch (e) {
      Logger.error('Script injection failed', e);
    }
  }

  // Start injection immediately
  initializeInjections();

  // ============================================================================
  // PASSIVE INTERCEPTION RELAY
  // ============================================================================
  /**
   * Window Message Listener
   * -----------------------
   * Listens for postMessage events from page context scripts.
   *
   * Message Types Handled:
   *
   * 1. ATHENA_API_INTERCEPT (from interceptor.js)
   *    Contains captured API response data
   *    Forwarded to background.js as API_CAPTURE
   *
   * 2. ACTIVE_FETCH_RESULT (from activeFetcher.js)
   *    Contains results of on-demand fetch requests
   *    Forwarded to background.js for processing
   *
   * Security Note:
   * We check event.source === window to ensure messages come from
   * the same window, not from iframes or other origins.
   */
  window.addEventListener('message', function(event) {
    // Only accept messages from same window (not iframes)
    if (event.source !== window) return;

    // Handle passive interception from interceptor.js
    if (event.data?.type === 'ATHENA_API_INTERCEPT') {
      passiveMessageCount++;
      const payload = event.data.payload;

      Logger.success(`Passive intercept #${passiveMessageCount}`, {
        method: payload.method,
        url: payload.url?.substring(0, 50) + '...'
      });

      // Forward to background script -> backend
      safeSendMessage({
        type: 'API_CAPTURE',
        payload: payload
      });

      // Emit telemetry for observer
      emitTelemetry('forward', true, {
        method: payload.method,
        url: payload.url?.substring(0, 100),
        count: passiveMessageCount
      });
    }

    // Handle active fetch results from activeFetcher.js
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

  // ============================================================================
  // ACTIVE FETCH COMMAND RELAY
  // ============================================================================
  /**
   * Chrome Runtime Message Listener
   * --------------------------------
   * Listens for messages from the background script (service worker).
   *
   * Message Types Handled:
   *
   * ACTIVE_FETCH_COMMAND (from background.js)
   * - User requested on-demand data fetch via popup or frontend
   * - Contains: action (FETCH_PREOP, etc.), payload (MRN, etc.)
   * - Forwarded to page context via postMessage for activeFetcher.js
   *
   * Why Bridge Needed:
   * Background script cannot directly inject into page context.
   * Content script bridges: background -> postMessage -> page context
   */
  try {
    if (isContextValid()) {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        // Re-check validity on each message
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

        return true; // Keep message channel open for async response
      });
    }
  } catch (e) {
    Logger.warn('Failed to register message listener - extension may need refresh');
  }

  // ============================================================================
  // STATUS & DIAGNOSTICS
  // ============================================================================

  Logger.success('Content script ready');
  Logger.info('Modes: Passive Interception + Active Fetching');

  // Emit init telemetry
  emitTelemetry('init', true, { page: window.location.hostname });

  /**
   * Periodic Status Logging
   * -----------------------
   * Logs bridge activity every 60 seconds if there's been traffic.
   * Useful for debugging connection issues.
   */
  setInterval(() => {
    if (passiveMessageCount > 0 || activeCommandCount > 0) {
      Logger.info('Stats', {
        passiveIntercepts: passiveMessageCount,
        activeCommands: activeCommandCount
      });
    }
  }, 60000);

})();
