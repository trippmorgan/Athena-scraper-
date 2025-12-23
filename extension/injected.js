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
    writesCaptured: 0,  // POST/PUT operations (saves)
    errors: 0
  };

  // ============================================================
  // SESSION HEADER CAPTURE - Stores CSRF/session headers for active fetch
  // ============================================================
  const capturedSessionHeaders = {
    'X-CSRF-Token': null,
    'X-Athena-Session-ID': null,
    'X-Athena-Clientid': null,
    'X-Requested-With': null,
    lastUpdated: null,

    // Store captured headers
    capture(headers) {
      const headersToCapture = ['x-csrf-token', 'x-athena-session-id', 'x-athena-clientid', 'x-requested-with'];
      let captured = false;

      for (const [key, value] of headers) {
        const lowerKey = key.toLowerCase();
        if (headersToCapture.includes(lowerKey)) {
          // Normalize key to standard format
          const normalizedKey = lowerKey === 'x-csrf-token' ? 'X-CSRF-Token' :
                               lowerKey === 'x-athena-session-id' ? 'X-Athena-Session-ID' :
                               lowerKey === 'x-athena-clientid' ? 'X-Athena-Clientid' :
                               'X-Requested-With';

          if (this[normalizedKey] !== value) {
            this[normalizedKey] = value;
            captured = true;
            InjectedLogger.success(`Captured header: ${normalizedKey}`, value.substring(0, 20) + '...');
          }
        }
      }

      if (captured) {
        this.lastUpdated = new Date().toISOString();
      }
      return captured;
    },

    // Get headers object for use in active fetch
    getHeaders() {
      const headers = {};
      if (this['X-CSRF-Token']) headers['X-CSRF-Token'] = this['X-CSRF-Token'];
      if (this['X-Athena-Session-ID']) headers['X-Athena-Session-ID'] = this['X-Athena-Session-ID'];
      if (this['X-Athena-Clientid']) headers['X-Athena-Clientid'] = this['X-Athena-Clientid'];
      if (this['X-Requested-With']) headers['X-Requested-With'] = this['X-Requested-With'];
      return headers;
    },

    hasValidSession() {
      return !!(this['X-CSRF-Token'] || this['X-Athena-Session-ID']);
    }
  };

  // Expose captured headers globally for activeFetcher.js
  window.__shadowEhrSession = capturedSessionHeaders;

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

    // DOCUMENT & IMAGING CAPTURE - PDFs, CTA, MRI, Ultrasound, Surgical Notes, Pathology
    if (urlLower.includes('/document') ||
        urlLower.includes('/pdf') ||
        urlLower.includes('/report') ||
        urlLower.includes('/imaging') ||
        urlLower.includes('/radiology') ||
        urlLower.includes('/clinicaldocument') ||
        urlLower.includes('/operativenote') ||
        urlLower.includes('/procedurenote') ||
        urlLower.includes('/pathology') ||
        urlLower.includes('/labresult') ||
        urlLower.includes('/surgicalnote') ||
        urlLower.includes('sources=clinical_documents') ||
        urlLower.includes('sources=adminorders') ||
        urlLower.includes('sources=imaging_orders') ||
        urlLower.includes('sources=imaging_results') ||
        urlLower.includes('sources=lab_results') ||
        urlLower.includes('sources=procedure_notes') ||
        urlLower.includes('sources=operative_reports') ||
        urlLower.includes('sources=surgical_history') ||
        urlLower.includes('sources=documents') ||
        urlLower.includes('sources=chart_documents') ||
        urlLower.includes('sources=scanned_documents') ||
        urlLower.includes('sources=external_clinical_documents') ||
        urlLower.includes('documentid=') ||
        urlLower.includes('/clinicalresult') ||
        urlLower.includes('/testresult') ||
        urlLower.includes('/viewdocument') ||
        urlLower.includes('/getdocument')) {
      return true;
    }

    return false;
  }

  // Helper to classify document type
  function classifyDocumentType(url, data) {
    const urlLower = (url || '').toLowerCase();
    const dataStr = JSON.stringify(data || {}).toLowerCase();

    if (urlLower.includes('cta') || dataStr.includes('ct angiography') || dataStr.includes('cta ')) {
      return 'cta';
    }
    if (urlLower.includes('mri') || urlLower.includes('mra') || dataStr.includes('magnetic resonance')) {
      return 'mri';
    }
    if (urlLower.includes('ultrasound') || urlLower.includes('duplex') || dataStr.includes('duplex') || dataStr.includes('ultrasound')) {
      return 'ultrasound';
    }
    if (urlLower.includes('operative') || urlLower.includes('surgical') || dataStr.includes('operative note') || dataStr.includes('surgical note')) {
      return 'surgical';
    }
    if (urlLower.includes('pathology') || dataStr.includes('pathology') || dataStr.includes('biopsy')) {
      return 'pathology';
    }
    if (urlLower.includes('echo') || dataStr.includes('echocardiogram') || dataStr.includes('echo ')) {
      return 'echo';
    }
    if (urlLower.includes('xray') || urlLower.includes('x-ray') || dataStr.includes('x-ray') || dataStr.includes('radiograph')) {
      return 'xray';
    }
    if (urlLower.includes('lab') || dataStr.includes('laboratory')) {
      return 'lab_report';
    }
    if (urlLower.includes('.pdf') || dataStr.includes('application/pdf')) {
      return 'pdf';
    }
    return 'other';
  }

  // Check if this is a WRITE operation (save note, update chart, etc.)
  function isWriteOperation(url, method) {
    if (method !== 'POST' && method !== 'PUT' && method !== 'PATCH') return false;
    const urlLower = url.toLowerCase();

    // Athena write patterns - note saves, chart updates, orders, etc.
    return (
      urlLower.includes('/note') ||
      urlLower.includes('/document') ||
      urlLower.includes('/save') ||
      urlLower.includes('/update') ||
      urlLower.includes('/submit') ||
      urlLower.includes('/sign') ||
      urlLower.includes('/order') ||
      urlLower.includes('/charge') ||
      urlLower.includes('/claim') ||
      urlLower.includes('/encounter') ||
      urlLower.includes('/clinicalnote') ||
      urlLower.includes('/diagnosis') ||
      urlLower.includes('/procedure') ||
      urlLower.includes('/ax/chart') ||
      urlLower.includes('/ax/encounter') ||
      urlLower.includes('/ax/note') ||
      urlLower.includes('action=save') ||
      urlLower.includes('action=submit')
    );
  }

  // Helper to emit intercept event
  function emitIntercept(type, url, method, data, requestBody = null) {
    const isWrite = isWriteOperation(url, method);
    const documentType = classifyDocumentType(url, data);
    const isDocument = documentType !== 'other' ||
                       (url && url.toLowerCase().includes('document')) ||
                       (url && url.toLowerCase().includes('/report'));

    if (isWrite) {
      stats.writesCaptured++;
      InjectedLogger._log('warn', '📝', `WRITE OPERATION CAPTURED: ${method}`, {
        url: url.length > 70 ? url.substring(0, 70) + '...' : url,
        requestBodySize: requestBody ? JSON.stringify(requestBody).length : 0,
        responseSize: data ? JSON.stringify(data).length : 0
      });
    } else if (isDocument) {
      InjectedLogger._log('info', '📄', `DOCUMENT CAPTURED: ${documentType.toUpperCase()}`, {
        method: method,
        url: url.length > 70 ? url.substring(0, 70) + '...' : url,
        documentType: documentType,
        dataSize: data ? JSON.stringify(data).length : 0
      });
    } else {
      InjectedLogger.intercept(`${type} CAPTURED`, {
        method: method,
        url: url.length > 70 ? url.substring(0, 70) + '...' : url,
        dataType: typeof data,
        dataSize: data ? JSON.stringify(data).length : 0
      });
    }

    window.dispatchEvent(new CustomEvent('SHADOW_EHR_INTERCEPT', {
      detail: {
        type: type,
        url: url,
        method: method,
        payload: data,
        requestBody: requestBody,  // Include the request body for write operations
        isWriteOperation: isWrite,
        isDocument: isDocument,
        documentType: documentType,
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

    // CAPTURE REQUEST HEADERS from Athena API calls (before the fetch completes)
    // This captures the CSRF token and session headers that Athena's app includes
    if (shouldIntercept(url) && config?.headers) {
      try {
        const headers = config.headers instanceof Headers
          ? config.headers
          : new Headers(config.headers);
        capturedSessionHeaders.capture(headers);
      } catch (e) {
        InjectedLogger.debug('Could not parse request headers:', e.message);
      }
    }

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

  // Store for XHR request headers
  const xhrSetRequestHeader = XHR.setRequestHeader;

  XHR.setRequestHeader = function(name, value) {
    // Capture session headers from XHR calls
    if (!this._shadowHeaders) this._shadowHeaders = new Map();
    this._shadowHeaders.set(name, value);

    // Check if this is a session header to capture
    const lowerName = name.toLowerCase();
    if (['x-csrf-token', 'x-athena-session-id', 'x-athena-clientid', 'x-requested-with'].includes(lowerName)) {
      capturedSessionHeaders.capture([[name, value]]);
    }

    return xhrSetRequestHeader.apply(this, arguments);
  };

  XHR.open = function(method, url) {
    this._shadowMethod = method;
    this._shadowUrl = url;
    this._shadowHeaders = new Map(); // Reset headers for new request
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
  InjectedLogger.info('📖 READ Monitoring: /chart/*, /api/*, /patient*, /medication*, /lab*, /vital*');
  InjectedLogger.info('📖 READ Athena:     /ax/data, sources=active_medications, allergies, etc.');
  InjectedLogger.info('📄 DOCS Monitoring: /document, /report, /imaging, sources=imaging_results, etc.');
  InjectedLogger.info('📝 WRITE Monitoring: /note, /save, /submit, /sign, /order, /charge, /claim');
  InjectedLogger.info('═'.repeat(50));

  // --- 4. Periodic stats logging ---
  setInterval(() => {
    const total = stats.fetchIntercepted + stats.xhrIntercepted;
    if (total > 0 || stats.writesCaptured > 0) {
      InjectedLogger.info('INTERCEPT STATS', {
        fetchCaptured: stats.fetchIntercepted,
        xhrCaptured: stats.xhrIntercepted,
        totalCaptured: total,
        writeOperations: stats.writesCaptured,
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

  // Expose function to get captured writes
  window.__shadowEhrWrites = () => {
    console.log(`📝 Total write operations captured: ${stats.writesCaptured}`);
    return stats.writesCaptured;
  };

})();
