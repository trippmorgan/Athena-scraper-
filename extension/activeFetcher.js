// activeFetcher.js - Active data extraction engine
// Runs in page context (injected), performs authenticated fetches using session cookies

(function() {
  'use strict';

  const Logger = {
    _log: (level, emoji, msg, data) => {
      const time = new Date().toLocaleTimeString('en-US', { hour12: false });
      const prefix = `[Active Fetcher ${time}]`;
      const styles = {
        info: "color: #3b82f6; font-weight: bold;",
        success: "color: #10b981; font-weight: bold;",
        warn: "color: #f59e0b; font-weight: bold;",
        error: "color: #ef4444; font-weight: bold;",
        fetch: "color: #8b5cf6; font-weight: bold;"
      };
      const style = styles[level] || styles.info;
      data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
    },
    info: (msg, data) => Logger._log('info', 'ℹ️', msg, data),
    success: (msg, data) => Logger._log('success', '✅', msg, data),
    warn: (msg, data) => Logger._log('warn', '⚠️', msg, data),
    error: (msg, data) => Logger._log('error', '❌', msg, data),
    fetch: (msg, data) => Logger._log('fetch', '🎯', msg, data)
  };

  // ============================================================
  // ATHENA ENDPOINT CONFIGURATION
  // Discovered from actual AthenaNet traffic analysis
  // Pattern: /{practiceId}/{departmentId}/ax/{endpoint}
  // ============================================================
  const ATHENA_CONFIG = {
    // Base URL pattern - auto-detected from current page
    baseUrl: '', // Will be auto-detected

    // Practice and department IDs - discovered from your instance
    // These may vary by user/practice - will try to auto-detect
    practiceId: '8042',
    departmentId: '65',

    // Search endpoint - Athena uses chart IDs, not simple MRN search
    // The chart ID is typically visible in the URL when viewing a patient
    searchEndpoint: null, // No simple search - use chart ID from URL

    // Real Athena endpoints - {chartId} = patient chart ID, {encounterId} = encounter ID
    // Note: originating_page parameter is required by Athena's backend
    endpoints: {
      // Chart-level data (using /ax/data pattern with query params)
      securityLabels: '/{practiceId}/{departmentId}/ax/security_label/chart/{chartId}/security_labels',
      activeProblems: '/{practiceId}/{departmentId}/ax/data?sources=active_problems&sources=chart_overview_problems&originating_page=chartoverview&chart_id={chartId}',
      activeMedications: '/{practiceId}/{departmentId}/ax/data?sources=active_medications&request_priority=HIGH&originating_page=chartoverview&chart_id={chartId}',
      allergies: '/{practiceId}/{departmentId}/ax/data?sources=allergies&originating_page=chartoverview&chart_id={chartId}',
      vitals: '/{practiceId}/{departmentId}/ax/data?sources=measurements&originating_page=chartoverview&chart_id={chartId}',
      historicalProblems: '/{practiceId}/{departmentId}/ax/data?sources=historical_problems&originating_page=chartoverview&chart_id={chartId}',
      demographics: '/{practiceId}/{departmentId}/ax/data?sources=demographics&originating_page=chartoverview&chart_id={chartId}',

      // Document endpoints
      documents: '/{practiceId}/{departmentId}/ax/data?sources=external_document_links&originating_page=chartoverview&chart_id={chartId}',

      // Medication endpoints
      coumadin: '/{practiceId}/{departmentId}/ax/medications/persistence/chart_has_classic_coumadin_flowsheet?chart_id={chartId}',

      // Encounter-level data (requires encounterId)
      encounterDocs: '/{practiceId}/{departmentId}/ax/encounter/{encounterId}/image_documentation',
      encounterImages: '/{practiceId}/{departmentId}/ax/encounter/{encounterId}/jotter_images',
      encounterSummary: '/{practiceId}/{departmentId}/ax/encounter/generate_summary',

      // External APIs (different domains)
      problems: 'https://api.imohealth.com/problemlistmanagement/problems/categorize',
      clinicalData: 'https://hospitalclinicalnano.api.athena.io/clinicals-external-data/api/v1/external',
      patientRisk: 'https://patientrisk.api.athena.io/patient-ra-gaps_prode1/api/v1/ragaps/count'
    },

    // Vascular-specific document filters
    vascularFilters: {
      documentTypes: ['Cardiology', 'Vascular', 'Radiology', 'CT', 'MRI', 'Ultrasound', 'Angiogram'],
      medicationClasses: ['anticoagulant', 'antiplatelet', 'antithrombotic', 'statin'],
      labPanels: ['BMP', 'CBC', 'Coagulation', 'Lipid', 'Renal', 'Cardiac']
    }
  };

  // Auto-detect base URL and IDs from current page
  function detectBaseUrl() {
    const url = new URL(window.location.href);
    ATHENA_CONFIG.baseUrl = `${url.protocol}//${url.host}`;
    Logger.info('Base URL detected:', ATHENA_CONFIG.baseUrl);

    // Try to extract practice/department IDs from URL path
    // Pattern: /8042/65/... or similar
    const pathMatch = url.pathname.match(/^\/(\d+)\/(\d+)\//);
    if (pathMatch) {
      ATHENA_CONFIG.practiceId = pathMatch[1];
      ATHENA_CONFIG.departmentId = pathMatch[2];
      Logger.info('Practice/Department IDs detected:', {
        practiceId: ATHENA_CONFIG.practiceId,
        departmentId: ATHENA_CONFIG.departmentId
      });
    }
  }

  // Extract chart ID (patient ID) from current Athena URL
  function extractChartIdFromUrl() {
    const url = window.location.href;

    // Common Athena URL patterns for patient charts:
    // /chart/14077167/...
    // /ax/security_label/chart/14077167/...
    // ?chartid=14077167
    // ?chart_id=14077167
    // ?patientid=14077167

    const patterns = [
      /\/chart\/(\d+)/i,
      /chart[_-]?id[=:](\d+)/i,
      /patient[_-]?id[=:](\d+)/i,
      /\/(\d{6,12})(?:\/|$|\?)/  // 6-12 digit number in path
    ];

    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) {
        Logger.info('Chart ID extracted from URL:', match[1]);
        return match[1];
      }
    }

    // Also check for chart ID in page content (DOM)
    const chartElement = document.querySelector('[data-chartid], [data-chart-id], [data-patientid]');
    if (chartElement) {
      const chartId = chartElement.getAttribute('data-chartid') ||
                      chartElement.getAttribute('data-chart-id') ||
                      chartElement.getAttribute('data-patientid');
      if (chartId) {
        Logger.info('Chart ID extracted from DOM:', chartId);
        return chartId;
      }
    }

    Logger.warn('Could not extract chart ID from current page');
    return null;
  }

  // Build endpoint URL with current practice/department/chart IDs
  function buildEndpointUrl(endpointTemplate, chartId, encounterId) {
    let url = endpointTemplate
      .replace('{practiceId}', ATHENA_CONFIG.practiceId)
      .replace('{departmentId}', ATHENA_CONFIG.departmentId)
      .replace('{chartId}', chartId || '')
      .replace('{encounterId}', encounterId || '');

    // For relative URLs, prepend base URL
    if (url.startsWith('/')) {
      url = ATHENA_CONFIG.baseUrl + url;
    }

    return url;
  }

  // ============================================================
  // FETCH UTILITIES
  // ============================================================
  
  async function authenticatedFetch(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${ATHENA_CONFIG.baseUrl}${endpoint}`;
    
    Logger.fetch(`Fetching: ${url}`);
    
    try {
      const response = await fetch(url, {
        ...options,
        credentials: 'include', // Include session cookies
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      Logger.success(`Fetched: ${endpoint}`, { size: JSON.stringify(data).length });
      return { success: true, data, endpoint };
    } catch (error) {
      Logger.error(`Failed: ${endpoint}`, error.message);
      return { success: false, error: error.message, endpoint };
    }
  }

  // ============================================================
  // PATIENT SEARCH & EXTRACTION
  // ============================================================

  async function searchPatientByMRN(mrn) {
    Logger.info('Searching for patient by MRN:', mrn);
    
    // Try multiple search patterns - Athena may use different endpoints
    const searchPatterns = [
      `${ATHENA_CONFIG.searchEndpoint}?mrn=${encodeURIComponent(mrn)}`,
      `${ATHENA_CONFIG.searchEndpoint}?query=${encodeURIComponent(mrn)}`,
      `/api/patients?mrn=${encodeURIComponent(mrn)}`,
      `/chart/search?mrn=${encodeURIComponent(mrn)}`
    ];

    for (const pattern of searchPatterns) {
      const result = await authenticatedFetch(pattern);
      if (result.success && result.data) {
        // Try to extract patient ID from response
        const patientId = extractPatientId(result.data);
        if (patientId) {
          Logger.success('Patient ID found:', patientId);
          return { success: true, patientId, rawData: result.data };
        }
      }
    }

    return { success: false, error: 'Patient not found or search endpoint not configured' };
  }

  function extractPatientId(searchResult) {
    // Handle various response structures
    if (typeof searchResult === 'string') return searchResult;
    if (searchResult.patientId) return searchResult.patientId;
    if (searchResult.id) return searchResult.id;
    if (searchResult.patient?.id) return searchResult.patient.id;
    if (Array.isArray(searchResult) && searchResult[0]?.id) return searchResult[0].id;
    if (searchResult.results?.[0]?.id) return searchResult.results[0].id;
    if (searchResult.patients?.[0]?.id) return searchResult.patients[0].id;
    return null;
  }

  // ============================================================
  // BATCH FETCH - Core Active Extraction
  // ============================================================

  async function fetchAllPatientData(chartId, options = {}) {
    Logger.info('═'.repeat(50));
    Logger.info('BATCH FETCH INITIATED', { chartId, options });

    if (!chartId) {
      Logger.error('No chart ID provided - cannot fetch data');
      return { error: 'No chart ID provided' };
    }

    const endpoints = ATHENA_CONFIG.endpoints;
    const fetchPromises = [];
    const results = {};

    // Determine which endpoints to fetch (only chart-level, skip encounter-level unless we have encounterId)
    const chartEndpoints = ['securityLabels', 'activeProblems', 'activeMedications', 'allergies', 'vitals', 'demographics'];
    const endpointsToFetch = options.endpoints || chartEndpoints;

    for (const key of endpointsToFetch) {
      if (endpoints[key]) {
        // Use the new buildEndpointUrl function with proper placeholders
        const url = buildEndpointUrl(endpoints[key], chartId, options.encounterId);

        // Skip external APIs for now (they require different auth)
        if (url.startsWith('https://api.') || url.startsWith('https://hospital') || url.startsWith('https://patient')) {
          Logger.info(`Skipping external API: ${key}`);
          continue;
        }

        fetchPromises.push(
          authenticatedFetch(url).then(result => {
            results[key] = result;
          })
        );
      }
    }

    // Execute all fetches in parallel
    await Promise.allSettled(fetchPromises);

    Logger.info('═'.repeat(50));
    Logger.success('BATCH FETCH COMPLETE', {
      total: fetchPromises.length,
      successful: Object.values(results).filter(r => r.success).length,
      failed: Object.values(results).filter(r => !r.success).length
    });

    return results;
  }

  // Fetch data for currently viewed patient (uses URL extraction)
  async function fetchCurrentPatientData(options = {}) {
    Logger.info('Fetching data for current patient from URL');

    const chartId = extractChartIdFromUrl();
    if (!chartId) {
      return {
        success: false,
        error: 'No patient chart found - navigate to a patient chart in Athena first'
      };
    }

    Logger.success('Found chart ID:', chartId);
    const data = await fetchAllPatientData(chartId, options);

    return {
      success: true,
      chartId,
      data,
      source: 'url_extraction',
      timestamp: new Date().toISOString()
    };
  }

  // ============================================================
  // SURGICAL WORKFLOW EXTRACTION
  // ============================================================

  async function fetchPreOpData(patientId) {
    Logger.info('Fetching PRE-OP data for surgical workflow');
    
    const criticalEndpoints = [
      'demographics',
      'medications',  // For anticoagulant status
      'allergies',
      'problems',
      'labs',         // For renal function, coag panel
      'documents',    // For cardiac clearance docs
      'vitals'
    ];

    const data = await fetchAllPatientData(patientId, { endpoints: criticalEndpoints });
    
    // Post-process for surgical relevance
    return {
      raw: data,
      surgical: extractSurgicalRelevantData(data)
    };
  }

  async function fetchIntraOpData(patientId) {
    Logger.info('Fetching INTRA-OP data for surgical workflow');
    
    const endpoints = [
      'imaging',      // Vascular anatomy
      'procedures',   // Previous interventions
      'documents',    // Op notes, angiograms
      'allergies'     // Contrast allergies
    ];

    return await fetchAllPatientData(patientId, { endpoints });
  }

  async function fetchPostOpData(patientId) {
    Logger.info('Fetching POST-OP data for surgical workflow');
    
    const endpoints = [
      'medications',  // Discharge meds
      'orders',       // Pending orders
      'labs',         // Recent labs
      'vitals'        // Trends
    ];

    return await fetchAllPatientData(patientId, { endpoints });
  }

  // ============================================================
  // VASCULAR-SPECIFIC DATA EXTRACTION
  // ============================================================

  function extractSurgicalRelevantData(rawData) {
    const surgical = {
      antithrombotics: [],
      renalFunction: null,
      cardiacClearance: null,
      vascularHistory: [],
      criticalAllergies: [],
      coagulationStatus: null
    };

    // Extract antithrombotic medications
    if (rawData.medications?.success) {
      const meds = rawData.medications.data;
      const antithromboticKeywords = [
        'aspirin', 'plavix', 'clopidogrel', 'eliquis', 'apixaban',
        'xarelto', 'rivaroxaban', 'coumadin', 'warfarin', 'heparin',
        'lovenox', 'enoxaparin', 'pradaxa', 'dabigatran', 'brilinta',
        'ticagrelor', 'effient', 'prasugrel'
      ];
      
      surgical.antithrombotics = filterByKeywords(meds, antithromboticKeywords);
    }

    // Extract renal function from labs
    if (rawData.labs?.success) {
      const labs = rawData.labs.data;
      surgical.renalFunction = extractLabValues(labs, ['creatinine', 'egfr', 'bun']);
      surgical.coagulationStatus = extractLabValues(labs, ['pt', 'inr', 'ptt', 'aptt']);
    }

    // Look for cardiac clearance in documents
    if (rawData.documents?.success) {
      const docs = rawData.documents.data;
      surgical.cardiacClearance = filterByKeywords(docs, [
        'cardiac', 'cardiology', 'echo', 'stress test', 'ejection fraction',
        'clearance', 'preoperative'
      ]);
    }

    // Extract critical allergies
    if (rawData.allergies?.success) {
      const allergies = rawData.allergies.data;
      surgical.criticalAllergies = filterByKeywords(allergies, [
        'contrast', 'iodine', 'latex', 'heparin', 'protamine'
      ]);
    }

    return surgical;
  }

  function filterByKeywords(data, keywords) {
    if (!data) return [];
    const items = Array.isArray(data) ? data : [data];
    
    return items.filter(item => {
      const itemStr = JSON.stringify(item).toLowerCase();
      return keywords.some(kw => itemStr.includes(kw.toLowerCase()));
    });
  }

  function extractLabValues(labData, labNames) {
    if (!labData) return null;
    const results = {};
    const items = Array.isArray(labData) ? labData : [labData];
    
    for (const item of items) {
      const itemStr = JSON.stringify(item).toLowerCase();
      for (const name of labNames) {
        if (itemStr.includes(name.toLowerCase())) {
          results[name] = item;
        }
      }
    }
    
    return Object.keys(results).length > 0 ? results : null;
  }

  // ============================================================
  // MESSAGE HANDLING - Communication with content script
  // ============================================================

  function emitResult(action, data, callbackId) {
    window.postMessage({
      type: 'ACTIVE_FETCH_RESULT',
      action,
      payload: data,
      callbackId,  // Include callbackId for response correlation
      timestamp: new Date().toISOString()
    }, '*');
  }

  window.addEventListener('message', async (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== 'ACTIVE_FETCH_COMMAND') return;

    const { action, payload, callbackId } = event.data;
    Logger.info('Command received:', { action, payload, callbackId });

    try {
      let result;

      switch (action) {
        case 'SEARCH_MRN':
          result = await searchPatientByMRN(payload.mrn);
          break;

        case 'FETCH_ALL':
          result = await fetchAllPatientData(payload.patientId || payload.chartId);
          break;

        case 'FETCH_CURRENT':
          // Fetch data for currently viewed patient (extracts chart ID from URL)
          result = await fetchCurrentPatientData(payload);
          break;

        case 'FETCH_BY_MRN':
          // Strategy: First try to use MRN/chartId directly if it looks like a chart ID
          // Athena chart IDs are typically 8-digit numbers
          const providedId = payload.mrn || payload.chartId;

          if (providedId && /^\d{6,10}$/.test(providedId)) {
            // Looks like a chart ID - try direct fetch
            Logger.info('Input looks like chart ID - fetching directly:', providedId);
            const directData = await fetchAllPatientData(providedId);
            result = {
              success: true,
              chartId: providedId,
              data: directData,
              source: 'direct_chartid'
            };
          } else {
            // Try MRN search first
            Logger.info('Trying MRN search:', providedId);
            const searchResult = await searchPatientByMRN(providedId);

            if (searchResult.success) {
              result = {
                success: true,
                chartId: searchResult.patientId,
                data: await fetchAllPatientData(searchResult.patientId),
                source: 'mrn_search'
              };
            } else {
              // Fall back to current page extraction
              Logger.warn('MRN search failed - trying URL extraction');
              result = await fetchCurrentPatientData();
            }
          }
          break;

        case 'FETCH_PREOP':
          result = await fetchPreOpData(payload.patientId || payload.chartId);
          break;

        case 'FETCH_INTRAOP':
          result = await fetchIntraOpData(payload.patientId || payload.chartId);
          break;

        case 'FETCH_POSTOP':
          result = await fetchPostOpData(payload.patientId || payload.chartId);
          break;

        case 'CONFIGURE_ENDPOINTS':
          // Allow runtime endpoint configuration
          Object.assign(ATHENA_CONFIG.endpoints, payload.endpoints);
          result = { success: true, endpoints: ATHENA_CONFIG.endpoints };
          break;

        case 'GET_CONFIG':
          // Return current configuration for debugging
          result = {
            success: true,
            config: ATHENA_CONFIG,
            currentChartId: extractChartIdFromUrl()
          };
          break;

        default:
          result = { error: `Unknown action: ${action}` };
      }

      emitResult(action, result, callbackId);
    } catch (error) {
      Logger.error('Command failed:', error);
      emitResult(action, { success: false, error: error.message }, callbackId);
    }
  });

  // ============================================================
  // INITIALIZATION
  // ============================================================

  detectBaseUrl();
  Logger.success('Active Fetcher initialized and ready');
  Logger.info('Available actions: FETCH_CURRENT, FETCH_BY_MRN, FETCH_ALL, FETCH_PREOP, FETCH_INTRAOP, FETCH_POSTOP, GET_CONFIG');
  Logger.info('Tip: Use FETCH_CURRENT to grab data for the patient chart you are viewing');

  // Expose for debugging in console
  window.__activeFetcher = {
    searchPatientByMRN,
    fetchAllPatientData,
    fetchCurrentPatientData,
    fetchPreOpData,
    fetchIntraOpData,
    fetchPostOpData,
    extractChartIdFromUrl,
    buildEndpointUrl,
    config: ATHENA_CONFIG,

    // Quick test function - fetches current patient and logs results
    test: async (chartId) => {
      const id = chartId || extractChartIdFromUrl();
      if (!id) {
        console.log('❌ No chart ID - navigate to a patient or pass ID: __activeFetcher.test("14281440")');
        return;
      }
      console.log(`🚀 Testing fetch for chart ID: ${id}`);
      const result = await fetchAllPatientData(id);
      console.log('📊 Results:', result);

      // Summary
      const successful = Object.entries(result).filter(([k, v]) => v.success).map(([k]) => k);
      const failed = Object.entries(result).filter(([k, v]) => !v.success).map(([k]) => k);
      console.log(`✅ Success (${successful.length}):`, successful.join(', '));
      console.log(`❌ Failed (${failed.length}):`, failed.join(', '));
      return result;
    },

    // Update config at runtime without reloading
    updateEndpoint: (name, url) => {
      ATHENA_CONFIG.endpoints[name] = url;
      console.log(`✅ Updated endpoint '${name}' to: ${url}`);
    }
  };

})();