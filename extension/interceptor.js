// interceptor.js - Runs in page context, hooks fetch/XHR
(function() {
  'use strict';

  const CONFIG = {
    // Endpoints we care about (clinical data)
    capturePatterns: [
      '/chart/',
      '/patient/',
      '/encounter/',
      '/clinical/',
      '/medications/',
      '/allergies/',
      '/labs/',
      '/vitals/',
      '/problems/',
      '/documents/',
      '/orders/',
      '/results/',
      '/notes/',
      '/api/'
    ],
    // Skip these (UI noise, static assets, telemetry)
    ignorePatterns: [
      '/static/',
      '/assets/',
      '/analytics/',
      '/tracking/',
      '/telemetry/',
      'datadoghq.com',
      'datadog',
      'sentry.io',
      'google-analytics',
      'googletagmanager',
      'hotjar',
      'mixpanel',
      '.js',
      '.css',
      '.png',
      '.svg',
      '.woff',
      '.ico'
    ]
  };

  // Logging utility
  const Logger = {
    _log: (level, emoji, msg, data) => {
      const time = new Date().toLocaleTimeString('en-US', { hour12: false });
      const prefix = `[AthenaNet Bridge ${time}]`;
      const styles = {
        info: "color: #06b6d4; font-weight: bold;",
        success: "color: #10b981; font-weight: bold;",
        warn: "color: #f59e0b; font-weight: bold;",
        debug: "color: #a855f7;",
        capture: "color: #22c55e; font-weight: bold;"
      };
      const style = styles[level] || styles.info;
      data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
    },
    info: (msg, data) => Logger._log('info', 'ℹ️', msg, data),
    success: (msg, data) => Logger._log('success', '✅', msg, data),
    warn: (msg, data) => Logger._log('warn', '⚠️', msg, data),
    debug: (msg, data) => Logger._log('debug', '🔍', msg, data),
    capture: (msg, data) => Logger._log('capture', '🎯', msg, data)
  };

  // Stats tracking
  const stats = {
    fetchCaptured: 0,
    xhrCaptured: 0,
    ignored: 0,
    errors: 0
  };

  Logger.info('═'.repeat(50));
  Logger.info('Interceptor initializing...');
  Logger.info('Capture patterns:', CONFIG.capturePatterns);
  Logger.info('═'.repeat(50));

  function shouldCapture(url) {
    const urlStr = url.toString().toLowerCase();

    // Check ignore patterns first
    if (CONFIG.ignorePatterns.some(p => urlStr.includes(p))) {
      return false;
    }

    // Check capture patterns
    return CONFIG.capturePatterns.some(p => urlStr.includes(p));
  }

  function sendToContentScript(data) {
    Logger.capture('CAPTURED', {
      source: data.source,
      method: data.method,
      url: data.url.substring(0, 60) + '...',
      status: data.status,
      patientId: data.patientId,
      size: `${(data.size / 1024).toFixed(1)}KB`
    });

    window.postMessage({
      type: 'ATHENA_API_INTERCEPT',
      payload: data
    }, '*');
  }

  function extractPatientContext(url) {
    // Try to extract patient ID from URL patterns
    const patterns = [
      /patient[\/=](\d+)/i,
      /patientid[\/=](\d+)/i,
      /chart[\/=](\d+)/i,
      /encounter[\/=](\d+)/i
    ];
    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) {
        Logger.debug(`Patient ID extracted: ${match[1]}`);
        return match[1];
      }
    }
    return null;
  }

  // ============ FETCH INTERCEPTOR ============
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const [resource, options = {}] = args;
    // Safely extract URL - handle Request objects, strings, and URL objects
    let url;
    if (resource instanceof Request) {
      url = resource.url;
    } else if (resource instanceof URL) {
      url = resource.href;
    } else if (typeof resource === 'string') {
      url = resource;
    } else {
      url = String(resource || '');
    }
    const method = options.method || (resource instanceof Request ? resource.method : 'GET');

    Logger.debug(`fetch() ${method} ${url.substring(0, 50)}...`);

    const response = await originalFetch.apply(this, args);

    if (shouldCapture(url)) {
      try {
        const clone = response.clone();
        const contentType = clone.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
          clone.json().then(data => {
            stats.fetchCaptured++;
            sendToContentScript({
              source: 'fetch',
              method: method.toUpperCase(),
              url: url,
              status: response.status,
              timestamp: new Date().toISOString(),
              patientId: extractPatientContext(url),
              data: data,
              size: JSON.stringify(data).length
            });
          }).catch((e) => {
            stats.errors++;
            Logger.debug('JSON parse failed for fetch response');
          });
        }
      } catch (e) {
        stats.errors++;
        // Silent fail - don't break the app
      }
    } else {
      stats.ignored++;
    }

    return response;
  };

  Logger.success('fetch() interceptor installed');

  // ============ XHR INTERCEPTOR ============
  const originalXHROpen = XMLHttpRequest.prototype.open;
  const originalXHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._interceptMeta = { method, url };
    Logger.debug(`XHR.open() ${method} ${url ? url.substring(0, 50) : 'N/A'}...`);
    return originalXHROpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const meta = this._interceptMeta;

    if (meta && shouldCapture(meta.url)) {
      this.addEventListener('load', function() {
        try {
          const contentType = this.getResponseHeader('content-type') || '';
          if (contentType.includes('application/json')) {
            const data = JSON.parse(this.responseText);
            stats.xhrCaptured++;
            sendToContentScript({
              source: 'xhr',
              method: meta.method.toUpperCase(),
              url: meta.url,
              status: this.status,
              timestamp: new Date().toISOString(),
              patientId: extractPatientContext(meta.url),
              data: data,
              size: this.responseText.length
            });
          }
        } catch (e) {
          stats.errors++;
          // Silent fail
        }
      });
    } else if (meta) {
      stats.ignored++;
    }

    return originalXHRSend.apply(this, [body]);
  };

  Logger.success('XHR interceptor installed');

  // Ready message
  Logger.info('═'.repeat(50));
  Logger.success('INTERCEPTOR ACTIVE AND READY');
  Logger.info('═'.repeat(50));

  // Periodic stats
  setInterval(() => {
    const total = stats.fetchCaptured + stats.xhrCaptured;
    if (total > 0) {
      Logger.info('STATS', {
        fetchCaptured: stats.fetchCaptured,
        xhrCaptured: stats.xhrCaptured,
        total: total,
        ignored: stats.ignored,
        errors: stats.errors
      });
    }
  }, 60000);

  // Expose stats for debugging
  window.__athenaBridgeStats = () => {
    console.table(stats);
    return stats;
  };

})();
