/**
 * Athena Assistant - Main Integration
 *
 * Ties together the Claude API, Clinical Analyzer, and Overlay UI.
 * Connects to the existing Shadow EHR scraper to get patient data.
 */

// === EARLY LOAD LOGGING - FIRST THING ===
console.log('%c[Athena Assistant] 📦 athena-assistant.js LOADING...', 'color: #8b5cf6; font-weight: bold; font-size: 14px;');
console.log('%c[Athena Assistant] 🔍 Checking dependencies...', 'color: #8b5cf6; font-weight: bold;');
console.log('[Athena Assistant] ClaudeAPIClient defined:', typeof window.ClaudeAPIClient !== 'undefined');
console.log('[Athena Assistant] ClinicalAnalyzer defined:', typeof window.ClinicalAnalyzer !== 'undefined');
console.log('[Athena Assistant] AthenaOverlay defined:', typeof window.AthenaOverlay !== 'undefined');

try {
  // Import other modules (will be bundled or loaded separately)
  // In content script context, these are loaded via manifest

  // Logger for Claude integration
  const ClaudeLogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Claude Assistant ${time}]`;
    const styles = {
      info: "color: #8b5cf6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      data: "color: #06b6d4; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => ClaudeLogger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => ClaudeLogger._log('success', '✅', msg, data),
  warn: (msg, data) => ClaudeLogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => ClaudeLogger._log('error', '❌', msg, data),
  data: (msg, data) => ClaudeLogger._log('data', '📦', msg, data)
};

// Expose class globally
window.AthenaAssistant = class AthenaAssistant {
  constructor() {
    this.api = null;
    this.analyzer = null;
    this.overlay = null;
    this.isInitialized = false;
    this.patientCache = {};

    // Keyboard shortcut to toggle overlay
    this.shortcutKey = 'KeyA'; // Alt+A to toggle

    // Debounce toggle to prevent rapid fire from multiple frames
    this.lastToggleTime = 0;
    this.toggleDebounceMs = 300;

    ClaudeLogger.info('AthenaAssistant constructor called');
  }

  /**
   * Debounced toggle - prevents multiple rapid toggles from iframes
   */
  debouncedToggle() {
    console.log('%c[Athena Assistant] 🔔 debouncedToggle() called', 'color: #8b5cf6; font-weight: bold;');
    const now = Date.now();
    const timeSinceLastToggle = now - this.lastToggleTime;
    console.log('[Athena Assistant] Time since last toggle:', timeSinceLastToggle, 'ms (debounce:', this.toggleDebounceMs, 'ms)');

    if (timeSinceLastToggle < this.toggleDebounceMs) {
      console.log('[Athena Assistant] Toggle DEBOUNCED (too fast)');
      ClaudeLogger.info('Toggle debounced (too fast, ignoring)');
      return false;
    }

    this.lastToggleTime = now;
    console.log('[Athena Assistant] Debounce passed, checking overlay...');
    console.log('[Athena Assistant] this.overlay exists:', !!this.overlay);

    if (!this.overlay) {
      console.error('[Athena Assistant] ❌ Cannot toggle - overlay is null!');
      return false;
    }

    console.log('[Athena Assistant] Calling overlay.toggle()...');
    ClaudeLogger.info('Debounced toggle executing');
    this.overlay.toggle();
    console.log('[Athena Assistant] toggle() call complete');
    return true;
  }

  /**
   * Initialize the assistant
   */
  async init() {
    console.log('%c[Athena Assistant] 🎬 init() called', 'color: #8b5cf6; font-weight: bold;');

    if (this.isInitialized) {
      ClaudeLogger.warn('Already initialized, skipping');
      return;
    }

    ClaudeLogger.info('=== INITIALIZATION STARTING ===');

    try {
      // Step 1: Initialize Claude API client
      console.log('[Athena Assistant] Step 1/7: Creating API client...');
      if (typeof window.ClaudeAPIClient === 'undefined') {
        ClaudeLogger.error('ClaudeAPIClient not loaded!');
        console.error('[Athena Assistant] FATAL: ClaudeAPIClient class is undefined');
        return;
      }
      this.api = new window.ClaudeAPIClient();
      console.log('[Athena Assistant] Step 1/7: ✓ API client created');

      // Step 2: Initialize Clinical Analyzer
      console.log('[Athena Assistant] Step 2/7: Creating Clinical Analyzer...');
      if (typeof window.ClinicalAnalyzer === 'undefined') {
        ClaudeLogger.error('ClinicalAnalyzer not loaded!');
        console.error('[Athena Assistant] FATAL: ClinicalAnalyzer class is undefined');
        return;
      }
      this.analyzer = new window.ClinicalAnalyzer(this.api);
      console.log('[Athena Assistant] Step 2/7: ✓ Clinical analyzer created');

      // Step 3: Initialize Overlay UI
      console.log('[Athena Assistant] Step 3/7: Creating Overlay UI...');
      if (typeof window.AthenaOverlay === 'undefined') {
        ClaudeLogger.error('AthenaOverlay not loaded!');
        console.error('[Athena Assistant] FATAL: AthenaOverlay class is undefined');
        return;
      }
      this.overlay = new window.AthenaOverlay();
      console.log('[Athena Assistant] Step 3a/7: ✓ Overlay instance created');
      this.overlay.init(this.api, this.analyzer);
      console.log('[Athena Assistant] Step 3b/7: ✓ Overlay initialized');

      // Step 4: Setup keyboard shortcut
      console.log('[Athena Assistant] Step 4/7: Setting up keyboard shortcut...');
      this.setupKeyboardShortcut();
      console.log('[Athena Assistant] Step 4/7: ✓ Keyboard shortcut ready');

      // Step 5: Listen for patient data from Shadow EHR
      console.log('[Athena Assistant] Step 5/7: Setting up patient data listener...');
      this.setupPatientDataListener();
      console.log('[Athena Assistant] Step 5/7: ✓ Patient data listener ready');

      // Step 6: Check for API key (ensure it's loaded from storage)
      console.log('[Athena Assistant] Step 6/7: Loading and checking API key...');
      await this.api.ensureApiKey();
      await this.checkApiKey();
      console.log('[Athena Assistant] Step 6/7: ✓ API key check complete');

      // Listen for API key changes (user saves key in popup)
      this.setupApiKeyListener();

      // Step 7: Try to detect current patient from URL
      console.log('[Athena Assistant] Step 7/7: Detecting current patient...');
      this.detectCurrentPatient();
      console.log('[Athena Assistant] Step 7/7: ✓ Patient detection complete');

      // Bonus: Watch for URL changes (SPA navigation)
      this.setupUrlWatcher();

      this.isInitialized = true;
      console.log('%c[Athena Assistant] ✅ === INITIALIZATION COMPLETE ===', 'color: #10b981; font-weight: bold; font-size: 14px;');
      console.log('%c[Athena Assistant] 🎹 Press Option+A (Mac) or Alt+A (Windows) to toggle overlay', 'color: #8b5cf6; font-weight: bold;');
      ClaudeLogger.success('Initialization complete! Press Alt+A to toggle overlay');
    } catch (e) {
      console.error('%c[Athena Assistant] ❌ init() FAILED:', 'color: #ef4444; font-weight: bold; font-size: 14px;', e.message);
      console.error('[Athena Assistant] Error stack:', e.stack);
      ClaudeLogger.error('Initialization failed:', e.message);
    }
  }

  /**
   * Listen for API key changes from storage (when user saves key in popup)
   */
  setupApiKeyListener() {
    try {
      chrome.storage.onChanged.addListener((changes, namespace) => {
        if (namespace === 'local' && changes.anthropicApiKey) {
          const newKey = changes.anthropicApiKey.newValue;
          if (newKey) {
            console.log('%c[Athena Assistant] 🔑 API key updated from storage!', 'color: #10b981; font-weight: bold;');
            this.api.apiKey = newKey;
            this.overlay?.addMessage('✅ API key configured! You can now use the AI assistant.');
            this.overlay?.setStatus('Ready');
          }
        }
      });
      ClaudeLogger.success('API key storage listener registered');
    } catch (e) {
      ClaudeLogger.warn('Could not register storage listener:', e.message);
    }
  }

  /**
   * Watch for URL changes to detect patient context switches
   */
  setupUrlWatcher() {
    let lastUrl = window.location.href;

    // Check URL periodically (handles SPA navigation)
    setInterval(() => {
      if (window.location.href !== lastUrl) {
        lastUrl = window.location.href;
        ClaudeLogger.info('URL changed, checking for patient...');
        this.detectCurrentPatient();
      }
    }, 1000);
    ClaudeLogger.info('URL watcher started');
  }

  /**
   * Setup keyboard shortcut (Alt+A) and toggle event listener
   */
  setupKeyboardShortcut() {
    console.log('[Athena Assistant] Setting up keyboard shortcut for:', this.shortcutKey);

    // DEBUG: Log ALL key presses to diagnose shortcut issues
    document.addEventListener('keydown', (e) => {
      // Log Alt key combinations
      if (e.altKey) {
        console.log('%c[Athena Assistant] ⌨️ Alt+key detected:', 'color: #f59e0b; font-weight: bold;', {
          code: e.code,
          key: e.key,
          altKey: e.altKey,
          ctrlKey: e.ctrlKey,
          metaKey: e.metaKey,
          shiftKey: e.shiftKey,
          target: e.target.tagName,
          expectedCode: this.shortcutKey,
          match: e.code === this.shortcutKey
        });
      }

      // Check for Alt+A (Option+A on Mac)
      if (e.altKey && e.code === this.shortcutKey) {
        e.preventDefault();
        e.stopPropagation();
        console.log('%c[Athena Assistant] ✅ Alt+A MATCHED! Toggling overlay...', 'color: #10b981; font-weight: bold; font-size: 14px;');
        ClaudeLogger.info('Alt+A pressed, toggling overlay');
        this.overlay.toggle();
        return;
      }

      // Also support just 'a' key check in case e.code is different
      if (e.altKey && (e.key === 'a' || e.key === 'A' || e.key === 'å' || e.key === '∑')) {
        // On Mac, Option+A produces 'å' character
        e.preventDefault();
        e.stopPropagation();
        console.log('%c[Athena Assistant] ✅ Alt+A (via e.key) MATCHED! Toggling overlay...', 'color: #10b981; font-weight: bold; font-size: 14px;');
        ClaudeLogger.info('Alt+A (key match) pressed, toggling overlay');
        this.overlay.toggle();
        return;
      }
    }, true); // Use capture phase to intercept before other handlers

    console.log('%c[Athena Assistant] ⌨️ Keyboard listener registered (capture phase)', 'color: #8b5cf6; font-weight: bold;');
    console.log('[Athena Assistant] Press Alt/Option+A to toggle overlay');

    // Listen for toggle event from injector.js (triggered by background/popup)
    // Use debounced toggle since multiple iframes may fire this event
    window.addEventListener('toggleAthenaAssistant', () => {
      console.log('%c[Athena Assistant] 📨 toggleAthenaAssistant event received!', 'color: #8b5cf6; font-weight: bold;');
      ClaudeLogger.info('Toggle event received from injector');
      this.debouncedToggle();
    });
    console.log('[Athena Assistant] toggleAthenaAssistant event listener registered');

    // NOTE: Removed duplicate chrome.runtime.onMessage listener for TOGGLE_OVERLAY
    // The injector.js already handles this and dispatches the toggleAthenaAssistant event
    // Having both caused double-toggle (show then immediately hide)

    ClaudeLogger.success('Keyboard shortcut (Alt+A) and toggle event listener registered');
  }

  /**
   * Listen for patient data from Shadow EHR scraper
   */
  setupPatientDataListener() {
    // Listen for custom events from injector.js (shadowEhrPatientUpdate) - same frame only
    window.addEventListener('shadowEhrPatientUpdate', (event) => {
      if (event.detail) {
        ClaudeLogger.data('Patient data event received (local)', {
          patientId: event.detail.patientId,
          medications: event.detail.medications?.length || 0,
          problems: event.detail.problems?.length || 0
        });
        this.handlePatientDataUpdate(event.detail);
      }
    });

    // CRITICAL: Listen for patient data from iframes via postMessage
    // The Claude overlay only runs in the top frame, but patient data is often
    // captured in iframes. injector.js sends this data via window.top.postMessage
    window.addEventListener('message', (event) => {
      // Log ALL messages to debug (temporarily)
      if (event.data?.type?.includes('SHADOW_EHR') || event.data?.type?.includes('PATIENT')) {
        console.log('%c[Athena Assistant] 📬 postMessage received:', 'color: #06b6d4; font-weight: bold;', {
          type: event.data?.type,
          origin: event.origin,
          hasDetail: !!event.data?.detail
        });
      }

      // Accept messages from athenahealth.com or same-origin iframes
      // The message type is specific enough that we can be more permissive
      if (event.data?.type === 'SHADOW_EHR_PATIENT_UPDATE_FROM_IFRAME') {
        ClaudeLogger.data('Patient data received FROM IFRAME', {
          patientId: event.data.detail?.patientId,
          medications: event.data.detail?.medications?.length || 0,
          problems: event.data.detail?.problems?.length || 0,
          origin: event.origin
        });
        if (event.data.detail) {
          this.handlePatientDataUpdate(event.data.detail);
        }
      }

      // Handle response to our data request
      if (event.data?.type === 'SHADOW_EHR_CACHED_DATA_RESPONSE') {
        ClaudeLogger.data('Cached data response from iframe', {
          patientId: event.data.detail?.patientId,
          hasData: !!event.data.detail
        });
        if (event.data.detail?.patientId) {
          this.handlePatientDataUpdate(event.data.detail);
        }
      }
    });

    // Request any cached data from iframes (handles timing issues)
    this.requestCachedDataFromFrames();

    ClaudeLogger.success('Patient data listener active (local + iframe messages)');
  }

  /**
   * Request cached patient data from all iframes
   * This handles the timing issue where iframes capture data before the overlay is ready
   */
  requestCachedDataFromFrames() {
    ClaudeLogger.info('Requesting cached patient data from frames...');

    // Request from top frame's injector cache (via chrome message)
    try {
      chrome.runtime.sendMessage({ type: 'GET_CACHED_PATIENT' }, (response) => {
        if (chrome.runtime.lastError) {
          ClaudeLogger.warn('Could not get cached patient from background:', chrome.runtime.lastError.message);
          return;
        }
        if (response?.success && response.data?.patientId) {
          ClaudeLogger.success('Got cached patient data from local frame:', response.data.patientId);
          this.handlePatientDataUpdate(response.data);
        }
      });
    } catch (e) {
      ClaudeLogger.warn('Error requesting cached patient:', e.message);
    }

    // Broadcast request to all iframes
    // They will respond via postMessage
    const iframes = document.querySelectorAll('iframe');
    ClaudeLogger.info(`Found ${iframes.length} iframes, requesting data...`);

    iframes.forEach((iframe, index) => {
      try {
        iframe.contentWindow?.postMessage({
          type: 'SHADOW_EHR_REQUEST_CACHED_DATA',
          requestId: `req-${Date.now()}-${index}`
        }, '*');
      } catch (e) {
        // Cross-origin iframe, can't post - this is fine
      }
    });

    // Also check if there's cached data in the local page context
    if (window.__shadowEhrPatientCache) {
      const cachedData = window.__shadowEhrPatientCache.getData();
      if (cachedData?.patientId) {
        ClaudeLogger.success('Found cached data in page context:', cachedData.patientId);
        this.handlePatientDataUpdate(cachedData);
      }
    }
  }

  /**
   * Handle patient data updates
   */
  handlePatientDataUpdate(data) {
    const patientId = data.patientId || data.patient_id;
    if (!patientId) {
      ClaudeLogger.warn('Patient data update with no patient ID');
      return;
    }

    ClaudeLogger.data('Patient data received', {
      patientId,
      hasPatient: !!data.patient,
      medications: data.medications?.length || 0,
      problems: data.problems?.length || 0,
      allergies: data.allergies?.length || 0
    });

    // Cache the data
    this.patientCache[patientId] = {
      ...this.patientCache[patientId],
      ...data,
      lastUpdated: new Date().toISOString()
    };

    // Update overlay with current patient
    if (this.overlay) {
      this.overlay.setPatientData(patientId, this.patientCache[patientId]);
    }
  }

  /**
   * Request patient data from backend cache
   */
  async requestPatientData(patientId) {
    ClaudeLogger.info('Requesting patient data from backend:', patientId);
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(
        { type: 'GET_PATIENT_DATA', patientId },
        (response) => {
          if (chrome.runtime.lastError) {
            ClaudeLogger.error('Chrome runtime error:', chrome.runtime.lastError.message);
            resolve(null);
            return;
          }
          if (response?.success && response.data) {
            ClaudeLogger.success('Got patient data from backend:', patientId);
            this.handlePatientDataUpdate({ patientId, ...response.data });
            resolve(response.data);
          } else {
            ClaudeLogger.warn('No backend data for:', patientId);
            resolve(null);
          }
        }
      );
    });
  }

  /**
   * Get all patients from backend cache
   */
  async getAllPatients() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(
        { type: 'GET_ALL_PATIENTS' },
        (response) => {
          if (chrome.runtime.lastError) {
            ClaudeLogger.error('Chrome runtime error:', chrome.runtime.lastError.message);
            resolve([]);
            return;
          }
          if (response?.success && response.patients) {
            ClaudeLogger.info('Got patients from backend:', response.patients.length);
            resolve(response.patients);
          } else {
            resolve([]);
          }
        }
      );
    });
  }

  /**
   * Try to detect current patient from URL
   */
  detectCurrentPatient() {
    const url = window.location.href;
    const patterns = [
      /\/chart\/(\d+)/i,
      /chart[_-]?id[=:](\d+)/i,
      /patient[_-]?id[=:](\d+)/i,
      /patientid=(\d+)/i,
      /\/(\d{6,10})(?:\/|$|\?)/
    ];

    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) {
        const patientId = match[1];
        ClaudeLogger.info('Detected patient from URL:', patientId);

        // Request data from backend if we don't have it
        if (!this.patientCache[patientId]) {
          this.requestPatientData(patientId);
        } else {
          if (this.overlay) {
            this.overlay.setPatientData(patientId, this.patientCache[patientId]);
          }
        }
        return patientId;
      }
    }
    ClaudeLogger.info('No patient ID found in URL');
    return null;
  }

  /**
   * Check if API key is configured
   */
  async checkApiKey() {
    ClaudeLogger.info('Checking API key...');
    const health = await this.api.healthCheck();
    if (!health.healthy) {
      ClaudeLogger.warn('API not configured:', health.reason);
      // Show setup message in overlay
      this.overlay.addMessage(
        '⚙️ **Setup Required**\n\n' +
        'Please configure your Claude API key:\n' +
        '1. Get an API key from console.anthropic.com\n' +
        '2. Click the extension icon\n' +
        '3. Enter your API key in settings\n\n' +
        'Until configured, AI features will be disabled.'
      );
    } else {
      console.log('[Athena Assistant] API configured and healthy');
    }
  }

  /**
   * Set API key programmatically
   */
  async setApiKey(key) {
    await this.api.setApiKey(key);
    const health = await this.api.healthCheck();
    return health;
  }

  /**
   * Get current patient data
   */
  getCurrentPatient() {
    return this.overlay.patientData;
  }

  /**
   * Quick access to clinical analysis
   */
  async analyzeCurrentPatient(analysisType = 'summary') {
    const data = this.getCurrentPatient();
    if (!data) {
      throw new Error('No patient data available');
    }

    switch (analysisType) {
      case 'medications':
        return this.analyzer.analyzeMedications(data);
      case 'risk':
        return this.analyzer.assessRisk(data);
      case 'alerts':
        return this.analyzer.identifyAlerts(data);
      case 'imaging':
        return this.analyzer.summarizeImaging(data);
      case 'summary':
      default:
        return this.analyzer.generatePreOpSummary(data);
    }
  }

  /**
   * Natural language query
   */
  async query(question) {
    const data = this.getCurrentPatient();
    if (!data) {
      throw new Error('No patient data available');
    }
    return this.analyzer.query(question, data);
  }

  /**
   * Debug mode - examine extension code and provide self-analysis
   * Usage: window.athenaAssistant.debugCode('injector') or debugCode('all')
   */
  async debugCode(component = 'all') {
    ClaudeLogger.info('Debug code analysis requested for:', component);

    // Map of components to their script locations
    const scripts = {
      injector: 'injector.js',
      interceptor: 'interceptor.js',
      activeFetcher: 'activeFetcher.js',
      apiClient: 'claude/api-client.js',
      clinicalAnalyzer: 'claude/clinical-analyzer.js',
      overlayUI: 'claude/overlay-ui.js',
      assistant: 'claude/athena-assistant.js',
      background: 'background.js'
    };

    const componentsToAnalyze = component === 'all'
      ? Object.keys(scripts)
      : [component];

    const codeContext = [];

    for (const comp of componentsToAnalyze) {
      const scriptPath = scripts[comp];
      if (!scriptPath) {
        ClaudeLogger.warn(`Unknown component: ${comp}`);
        continue;
      }

      try {
        const url = chrome.runtime.getURL(scriptPath);
        const response = await fetch(url);
        if (response.ok) {
          const code = await response.text();
          codeContext.push({
            component: comp,
            file: scriptPath,
            code: code.substring(0, 8000), // Limit size
            lines: code.split('\n').length
          });
          ClaudeLogger.success(`Loaded ${comp}: ${code.split('\n').length} lines`);
        }
      } catch (e) {
        ClaudeLogger.warn(`Could not load ${comp}:`, e.message);
      }
    }

    // Store for use in debug queries
    this.debugContext = {
      scripts: codeContext,
      timestamp: new Date().toISOString(),
      state: await this.diagnose()
    };

    console.log('%c[Debug Mode] Code context loaded:', 'color: #f472b6; font-weight: bold;', {
      components: codeContext.map(c => c.component),
      totalLines: codeContext.reduce((sum, c) => sum + c.lines, 0)
    });

    return this.debugContext;
  }

  /**
   * Ask Claude to analyze the extension code
   * Usage: window.athenaAssistant.analyzeCode('Why is patient data not reaching the overlay?')
   */
  async analyzeCode(question) {
    if (!this.debugContext) {
      ClaudeLogger.info('Loading code context first...');
      await this.debugCode('all');
    }

    if (!this.api?.apiKey) {
      console.error('API key required for code analysis');
      return;
    }

    const codeSnippets = this.debugContext.scripts
      .map(s => `=== ${s.file} (${s.lines} lines) ===\n${s.code}`)
      .join('\n\n');

    const prompt = `You are debugging a Chrome extension. Analyze the code and answer this question:

QUESTION: ${question}

CURRENT STATE:
${JSON.stringify(this.debugContext.state, null, 2)}

EXTENSION CODE:
${codeSnippets}

Provide a detailed analysis with:
1. Root cause identification
2. Data flow trace
3. Specific fix recommendations with line numbers
4. Any potential race conditions or timing issues`;

    ClaudeLogger.info('Sending code analysis request to Claude...');
    this.overlay?.addMessage(`🔍 Analyzing: ${question}`, true);
    this.overlay?.setStatus('Analyzing code...', 'thinking');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: `You are an expert Chrome extension debugger. You understand content scripts,
background workers, message passing, iframe communication, and the Chrome extension API.
Provide actionable debugging advice with specific code fixes.`,
        maxTokens: 4096,
        temperature: 0.2
      });

      if (result.success) {
        this.overlay?.addMessage(result.content);
        console.log('%c[Debug Analysis]', 'color: #f472b6; font-weight: bold;', result.content);
      } else {
        this.overlay?.addMessage(`Error: ${result.error}`);
      }
      this.overlay?.setStatus('Ready');
      return result;
    } catch (e) {
      ClaudeLogger.error('Code analysis failed:', e.message);
      return { success: false, error: e.message };
    }
  }

  /**
   * Diagnostic function - run from console: window.athenaAssistant.diagnose()
   */
  async diagnose() {
    console.log('%c╔══════════════════════════════════════════════════╗', 'color: #8b5cf6; font-weight: bold;');
    console.log('%c║     ATHENA ASSISTANT DIAGNOSTIC REPORT           ║', 'color: #8b5cf6; font-weight: bold;');
    console.log('%c╚══════════════════════════════════════════════════╝', 'color: #8b5cf6; font-weight: bold;');

    // Check initialization
    console.log('\n%c1. INITIALIZATION STATUS:', 'color: #f59e0b; font-weight: bold;');
    console.log('   isInitialized:', this.isInitialized);
    console.log('   API client exists:', !!this.api);
    console.log('   Analyzer exists:', !!this.analyzer);
    console.log('   Overlay exists:', !!this.overlay);

    // Check API key
    console.log('\n%c2. API KEY STATUS:', 'color: #f59e0b; font-weight: bold;');
    if (this.api) {
      console.log('   API key set:', !!this.api.apiKey);
      if (this.api.apiKey) {
        console.log('   API key prefix:', this.api.apiKey.substring(0, 12) + '...');
      } else {
        console.log('%c   ⚠️ NO API KEY CONFIGURED!', 'color: #ef4444; font-weight: bold;');
        console.log('   → Set your API key in the extension popup or run:');
        console.log('   → window.athenaAssistant.api.setApiKey("sk-ant-api...")');
      }

      // Health check
      console.log('\n%c3. API HEALTH CHECK:', 'color: #f59e0b; font-weight: bold;');
      try {
        const health = await this.api.healthCheck();
        console.log('   Healthy:', health.healthy);
        console.log('   Reason:', health.reason);
      } catch (e) {
        console.log('   Health check failed:', e.message);
      }
    }

    // Check patient data
    console.log('\n%c4. PATIENT DATA STATUS:', 'color: #f59e0b; font-weight: bold;');
    if (this.overlay) {
      console.log('   Current patient ID:', this.overlay.currentPatientId || 'None');
      console.log('   Patient data exists:', !!this.overlay.patientData);
      if (this.overlay.patientData) {
        console.log('   Medications:', this.overlay.patientData.medications?.length || 0);
        console.log('   Problems:', this.overlay.patientData.problems?.length || 0);
        console.log('   Allergies:', this.overlay.patientData.allergies?.length || 0);
      }
    }

    // Check overlay state
    console.log('\n%c5. OVERLAY STATE:', 'color: #f59e0b; font-weight: bold;');
    if (this.overlay) {
      console.log('   isOpen:', this.overlay.isOpen);
      console.log('   isMinimized:', this.overlay.isMinimized);
      console.log('   Container in DOM:', !!this.overlay.container && document.body.contains(this.overlay.container));
      console.log('   claudeAPI set:', !!this.overlay.claudeAPI);
      console.log('   clinicalAnalyzer set:', !!this.overlay.clinicalAnalyzer);
    }

    console.log('\n%c╔══════════════════════════════════════════════════╗', 'color: #10b981; font-weight: bold;');
    console.log('%c║     END OF DIAGNOSTIC REPORT                      ║', 'color: #10b981; font-weight: bold;');
    console.log('%c╚══════════════════════════════════════════════════╝', 'color: #10b981; font-weight: bold;');

    return {
      initialized: this.isInitialized,
      hasApi: !!this.api,
      hasApiKey: !!this.api?.apiKey,
      hasOverlay: !!this.overlay,
      hasPatientData: !!this.overlay?.patientData,
      overlayOpen: this.overlay?.isOpen
    };
  }
}

// Create and expose global instance
console.log('%c[Athena Assistant] 🔧 Creating AthenaAssistant instance...', 'color: #8b5cf6; font-weight: bold;');
const athenaAssistant = new AthenaAssistant();
console.log('%c[Athena Assistant] ✅ Instance created', 'color: #10b981; font-weight: bold;');

// Auto-initialize when DOM is ready
console.log('[Athena Assistant] document.readyState:', document.readyState);
if (document.readyState === 'loading') {
  console.log('[Athena Assistant] DOM still loading, waiting for DOMContentLoaded...');
  document.addEventListener('DOMContentLoaded', () => {
    console.log('%c[Athena Assistant] 🚀 DOMContentLoaded fired, calling init()...', 'color: #8b5cf6; font-weight: bold;');
    athenaAssistant.init();
  });
} else {
  console.log('%c[Athena Assistant] 🚀 DOM ready, calling init() immediately...', 'color: #8b5cf6; font-weight: bold;');
  athenaAssistant.init();
}

// Expose to window for debugging and external access
window.athenaAssistant = athenaAssistant;
console.log('[Athena Assistant] Exposed window.athenaAssistant:', !!window.athenaAssistant);

// Export
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AthenaAssistant, athenaAssistant };
}

console.log('%c[Athena Assistant] ✅ athena-assistant.js LOADED SUCCESSFULLY', 'color: #10b981; font-weight: bold; font-size: 14px;');

} catch (e) {
  console.error('%c[Athena Assistant] ❌ athena-assistant.js FAILED TO LOAD:', 'color: #ef4444; font-weight: bold; font-size: 14px;', e.message);
  console.error('[Athena Assistant] Error stack:', e.stack);
}
