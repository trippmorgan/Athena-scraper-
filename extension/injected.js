/**
 * Tier 1: The "Hook"
 * This script runs in the 'Main World' context (same as Athena's React/Angular app).
 * It monkey-patches the native networking APIs to capture data in flight.
 */

(function() {
  // Logger for Main World (injected context)
  const InjectedLogger = {
    _log: (level, emoji, msg, data) => {
      const time = new Date().toLocaleTimeString('en-US', { hour12: false });
      const prefix = `[Shadow EHR Hook ${time}]`;
      const styles = {
        info: "color: #06b6d4; font-weight: bold;",
        success: "color: #10b981; font-weight: bold;",
        warn: "color: #f59e0b; font-weight: bold;",
        error: "color: #ef4444; font-weight: bold;",
        debug: "color: #a855f7;",
        intercept: "color: #22c55e; font-weight: bold;"
      };
      const style = styles[level] || styles.info;
      data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
    },
    info: (msg, data) => InjectedLogger._log('info', 'ℹ️', msg, data),
    success: (msg, data) => InjectedLogger._log('success', '✅', msg, data),
    warn: (msg, data) => InjectedLogger._log('warn', '⚠️', msg, data),
    error: (msg, data) => InjectedLogger._log('error', '❌', msg, data),
    debug: (msg, data) => InjectedLogger._log('debug', '🔍', msg, data),
    intercept: (msg, data) => InjectedLogger._log('intercept', '🎯', msg, data)
  };

  // Statistics
  let stats = {
    fetchIntercepted: 0,
    xhrIntercepted: 0,
    fetchIgnored: 0,
    xhrIgnored: 0,
    errors: 0
  };

  InjectedLogger.info('═'.repeat(50));
  InjectedLogger.info('Shadow EHR Interceptor Initializing...');
  InjectedLogger.info('Running in Main World context');
  InjectedLogger.info('═'.repeat(50));

  const XHR = XMLHttpRequest.prototype;
  const open = XHR.open;
  const send = XHR.send;
  const originalFetch = window.fetch;

  // Helper to check if URL should be intercepted
  // CRITICAL: Must include Athena-specific patterns for medication/lab/allergy data
  function shouldIntercept(url) {
    if (typeof url !== 'string') return false;
    const urlLower = url.toLowerCase();

    // Standard clinical patterns
    if (urlLower.includes('/chart/') ||
        urlLower.includes('/api/') ||
        urlLower.includes('/patient') ||
        urlLower.includes('/clinical') ||
        urlLower.includes('/encounter') ||
        urlLower.includes('/medication') ||
        urlLower.includes('/allerg') ||
        urlLower.includes('/lab') ||
        urlLower.includes('/vital') ||
        urlLower.includes('/problem') ||
        urlLower.includes('/document') ||
        urlLower.includes('/note') ||
        urlLower.includes('/order') ||
        urlLower.includes('/result')) {
      return true;
    }

    // Athena-specific patterns (CRITICAL for surgical data!)
    // Pattern: /ax/data?sources=<type>&...
    if (urlLower.includes('/ax/data') ||
        urlLower.includes('/ax/security_label') ||
        urlLower.includes('/ax/medications') ||
        urlLower.includes('/ax/encounter') ||
        urlLower.includes('sources=active_medications') ||
        urlLower.includes('sources=active_problems') ||
        urlLower.includes('sources=historical_problems') ||
        urlLower.includes('sources=chart_overview_problems') ||
        urlLower.includes('sources=allergies') ||
        urlLower.includes('sources=measurements') ||
        urlLower.includes('sources=demographics') ||
        urlLower.includes('sources=external_document')) {
      return true;
    }

    return false;
  }

  // Helper to emit intercept event
  function emitIntercept(type, url, method, data) {
    InjectedLogger.intercept(`${type} CAPTURED`, {
      method: method,
      url: url.length > 70 ? url.substring(0, 70) + '...' : url,
      dataType: typeof data,
      dataSize: data ? JSON.stringify(data).length : 0
    });

    window.dispatchEvent(new CustomEvent('SHADOW_EHR_INTERCEPT', {
      detail: {
        type: type,
        url: url,
        method: method,
        payload: data,
        timestamp: new Date().toISOString()
      }
    }));
  }

  // --- 1. Hook window.fetch ---
  InjectedLogger.debug('Patching window.fetch...');

  window.fetch = async function(...args) {
    const [resource, config] = args;
    const url = typeof resource === 'string' ? resource : resource.url || '';
    const method = config?.method || 'GET';

    InjectedLogger.debug(`fetch() called: ${method} ${url.substring(0, 50)}...`);

    const response = await originalFetch.apply(this, args);

    // Clone response to read body without consuming the stream for the app
    const clone = response.clone();

    clone.json().then(data => {
      if (shouldIntercept(url)) {
        stats.fetchIntercepted++;
        emitIntercept('FETCH', url, method, data);

        // Log data preview
        if (typeof data === 'object' && data !== null) {
          const keys = Object.keys(data).slice(0, 5);
          InjectedLogger.debug('Response keys:', keys);
        }
      } else {
        stats.fetchIgnored++;
        InjectedLogger.debug(`fetch ignored (not clinical): ${url.substring(0, 40)}...`);
      }
    }).catch(err => {
      // Ignore non-JSON responses (html, images, etc)
      stats.errors++;
      InjectedLogger.debug(`fetch response not JSON: ${url.substring(0, 40)}...`);
    });

    return response;
  };

  InjectedLogger.success('window.fetch patched successfully');

  // --- 2. Hook XMLHttpRequest (Legacy Athena components) ---
  InjectedLogger.debug('Patching XMLHttpRequest...');

  XHR.open = function(method, url) {
    this._shadowMethod = method;
    this._shadowUrl = url;
    InjectedLogger.debug(`XHR.open(): ${method} ${url ? url.substring(0, 50) : 'N/A'}...`);
    return open.apply(this, arguments);
  };

  XHR.send = function(postData) {
    this.addEventListener('load', function() {
      const url = this._shadowUrl || '';
      const method = this._shadowMethod || 'GET';

      if (shouldIntercept(url)) {
        try {
          if (this.responseType === '' || this.responseType === 'text') {
            const data = JSON.parse(this.responseText);
            stats.xhrIntercepted++;
            emitIntercept('XHR', url, method, data);

            // Log data preview
            if (typeof data === 'object' && data !== null) {
              const keys = Object.keys(data).slice(0, 5);
              InjectedLogger.debug('XHR Response keys:', keys);
            }
          }
        } catch (err) {
          stats.errors++;
          InjectedLogger.debug(`XHR response not JSON: ${url.substring(0, 40)}...`);
        }
      } else {
        stats.xhrIgnored++;
        InjectedLogger.debug(`XHR ignored (not clinical): ${url.substring(0, 40)}...`);
      }
    });
    return send.apply(this, arguments);
  };

  InjectedLogger.success('XMLHttpRequest patched successfully');

  // --- 3. Ready message ---
  InjectedLogger.info('═'.repeat(50));
  InjectedLogger.success('INTERCEPTOR ACTIVE AND READY');
  InjectedLogger.info('Monitoring standard: /chart/*, /api/*, /patient*, /clinical*, /medication*, /lab*, /vital*');
  InjectedLogger.info('Monitoring Athena:  /ax/data, sources=active_medications, sources=allergies, etc.');
  InjectedLogger.info('═'.repeat(50));

  // --- 4. Periodic stats logging ---
  setInterval(() => {
    const total = stats.fetchIntercepted + stats.xhrIntercepted;
    if (total > 0) {
      InjectedLogger.info('INTERCEPT STATS', {
        fetchCaptured: stats.fetchIntercepted,
        xhrCaptured: stats.xhrIntercepted,
        totalCaptured: total,
        ignored: stats.fetchIgnored + stats.xhrIgnored,
        errors: stats.errors
      });
    }
  }, 60000); // Every minute

  // Expose stats for debugging
  window.__shadowEhrStats = () => {
    console.table(stats);
    return stats;
  };

})();
