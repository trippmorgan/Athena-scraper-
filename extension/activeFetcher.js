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
  // These need to be discovered by inspecting network traffic
  // Update these patterns based on your Athena instance
  // ============================================================
  const ATHENA_CONFIG = {
    // Base URL pattern - update to match your Athena instance
    baseUrl: '', // Will be auto-detected from current page
    
    // Search endpoint to convert MRN -> Internal Patient ID
    searchEndpoint: '/api/v1/patients/search',
    
    // Data endpoints - {patientId} will be replaced
    endpoints: {
      demographics: '/api/v1/chart/{patientId}/demographics',
      medications: '/api/v1/chart/{patientId}/medications',
      problems: '/api/v1/chart/{patientId}/problems',
      allergies: '/api/v1/chart/{patientId}/allergies',
      vitals: '/api/v1/chart/{patientId}/vitals',
      labs: '/api/v1/chart/{patientId}/labs',
      documents: '/api/v1/chart/{patientId}/documents',
      encounters: '/api/v1/chart/{patientId}/encounters',
      orders: '/api/v1/chart/{patientId}/orders',
      procedures: '/api/v1/chart/{patientId}/procedures',
      imaging: '/api/v1/chart/{patientId}/imaging',
      notes: '/api/v1/chart/{patientId}/notes'
    },

    // Vascular-specific document filters
    vascularFilters: {
      documentTypes: ['Cardiology', 'Vascular', 'Radiology', 'CT', 'MRI', 'Ultrasound', 'Angiogram'],
      medicationClasses: ['anticoagulant', 'antiplatelet', 'antithrombotic', 'statin'],
      labPanels: ['BMP', 'CBC', 'Coagulation', 'Lipid', 'Renal', 'Cardiac']
    }
  };

  // Auto-detect base URL from current page
  function detectBaseUrl() {
    const url = new URL(window.location.href);
    ATHENA_CONFIG.baseUrl = `${url.protocol}//${url.host}`;
    Logger.info('Base URL detected:', ATHENA_CONFIG.baseUrl);
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

  async function fetchAllPatientData(patientId, options = {}) {
    Logger.info('═'.repeat(50));
    Logger.info('BATCH FETCH INITIATED', { patientId, options });
    
    const endpoints = ATHENA_CONFIG.endpoints;
    const fetchPromises = [];
    const results = {};

    // Determine which endpoints to fetch
    const endpointsToFetch = options.endpoints || Object.keys(endpoints);

    for (const key of endpointsToFetch) {
      if (endpoints[key]) {
        const url = endpoints[key].replace('{patientId}', patientId);
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
      total: endpointsToFetch.length,
      successful: Object.values(results).filter(r => r.success).length,
      failed: Object.values(results).filter(r => !r.success).length
    });

    return results;
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
          result = await fetchAllPatientData(payload.patientId);
          break;

        case 'FETCH_BY_MRN':
          // Combined: Search + Fetch All
          const searchResult = await searchPatientByMRN(payload.mrn);
          if (searchResult.success) {
            result = {
              patientId: searchResult.patientId,
              data: await fetchAllPatientData(searchResult.patientId)
            };
          } else {
            result = searchResult;
          }
          break;

        case 'FETCH_PREOP':
          result = await fetchPreOpData(payload.patientId);
          break;

        case 'FETCH_INTRAOP':
          result = await fetchIntraOpData(payload.patientId);
          break;

        case 'FETCH_POSTOP':
          result = await fetchPostOpData(payload.patientId);
          break;

        case 'CONFIGURE_ENDPOINTS':
          // Allow runtime endpoint configuration
          Object.assign(ATHENA_CONFIG.endpoints, payload.endpoints);
          result = { success: true, endpoints: ATHENA_CONFIG.endpoints };
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
  Logger.info('Available actions: SEARCH_MRN, FETCH_ALL, FETCH_BY_MRN, FETCH_PREOP, FETCH_INTRAOP, FETCH_POSTOP');

  // Expose for debugging
  window.__activeFetcher = {
    searchPatientByMRN,
    fetchAllPatientData,
    fetchPreOpData,
    fetchIntraOpData,
    fetchPostOpData,
    config: ATHENA_CONFIG
  };

})();