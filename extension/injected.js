/**
 * Tier 1: The "Hook"
 * This script runs in the 'Main World' context (same as Athena's React/Angular app).
 * It monkey-patches the native networking APIs to capture data in flight.
 */

(function() {
    const XHR = XMLHttpRequest.prototype;
    const open = XHR.open;
    const send = XHR.send;
    const originalFetch = window.fetch;
  
    // --- 1. Hook window.fetch ---
    window.fetch = async function(...args) {
      const [resource, config] = args;
      const response = await originalFetch.apply(this, args);
  
      // Clone response to read body without consuming the stream for the app
      const clone = response.clone();
      
      clone.json().then(data => {
          // Only emit relevant internal API calls
          // We filter slightly here to reduce noise, but mostly handled in Python
          if (typeof resource === 'string' && (resource.includes('/chart/') || resource.includes('/api/'))) {
            window.dispatchEvent(new CustomEvent('SHADOW_EHR_INTERCEPT', { 
                detail: {
                    type: 'FETCH',
                    url: resource,
                    method: config?.method || 'GET',
                    payload: data,
                    timestamp: new Date().toISOString()
                }
            }));
          }
      }).catch(err => {
          // Ignore non-JSON responses (html, images, etc)
      });
  
      return response;
    };
  
    // --- 2. Hook XMLHttpRequest (Legacy Athena components) ---
    XHR.open = function(method, url) {
      this._method = method;
      this._url = url;
      return open.apply(this, arguments);
    };
  
    XHR.send = function(postData) {
      this.addEventListener('load', function() {
        const url = this._url ? this._url.toLowerCase() : '';
        if (url.includes('/chart/') || url.includes('/api/')) {
            try {
                if (this.responseType === '' || this.responseType === 'text') {
                    const data = JSON.parse(this.responseText);
                    window.dispatchEvent(new CustomEvent('SHADOW_EHR_INTERCEPT', { 
                        detail: {
                            type: 'XHR',
                            url: this._url,
                            method: this._method,
                            payload: data,
                            timestamp: new Date().toISOString()
                        }
                    }));
                }
            } catch (err) {
                // Response wasn't JSON
            }
        }
      });
      return send.apply(this, arguments);
    };
    
    console.log("%c[Shadow EHR] Interceptor Active", "color: #00a3cc; font-weight: bold; font-size: 12px;");
  
  })();