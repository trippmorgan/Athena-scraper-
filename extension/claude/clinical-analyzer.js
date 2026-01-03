/**
 * Clinical Analyzer - Option A
 *
 * AI-powered clinical analysis for vascular surgery workflows.
 * Provides risk assessment, medication analysis, and natural language queries.
 */

// === EARLY LOAD LOGGING ===
console.log('%c[Clinical Analyzer] 📦 clinical-analyzer.js LOADING...', 'color: #14b8a6; font-weight: bold; font-size: 14px;');

try {
  // Logger for analyzer debugging
const AnalyzerLogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Clinical Analyzer ${time}]`;
    const styles = {
      info: "color: #14b8a6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      analysis: "color: #f472b6; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => AnalyzerLogger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => AnalyzerLogger._log('success', '✅', msg, data),
  warn: (msg, data) => AnalyzerLogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => AnalyzerLogger._log('error', '❌', msg, data),
  analysis: (msg, data) => AnalyzerLogger._log('analysis', '🔬', msg, data)
};

// System prompts for different analysis modes
const SYSTEM_PROMPTS = {
  vascularExpert: `You are an expert vascular surgery clinical assistant. You help analyze patient data for pre-operative planning, risk assessment, and clinical decision support.

Key responsibilities:
- Identify antithrombotic medications and recommend hold times before surgery
- Calculate surgical risk (RCRI, bleeding risk, contrast nephropathy risk)
- Flag critical findings that require immediate attention
- Summarize relevant vascular history and imaging findings
- Provide evidence-based recommendations

Always be concise and clinically precise. Use standard medical abbreviations.
Format critical alerts prominently. Include relevant ICD-10 codes when applicable.`,

  medicationAnalysis: `You are analyzing medications for a vascular surgery patient. Focus on:
- Antiplatelets (Aspirin, Clopidogrel/Plavix, Prasugrel, Ticagrelor)
- Anticoagulants (Warfarin, Apixaban/Eliquis, Rivaroxaban/Xarelto, Dabigatran/Pradaxa)
- Hold recommendations before surgery
- Bridging requirements
- Reversal agents if emergent surgery needed

Provide a clear, actionable medication management plan.`,

  riskAssessment: `You are calculating perioperative risk for a vascular surgery patient. Consider:
- Revised Cardiac Risk Index (RCRI) components
- Bleeding risk factors
- Renal function and contrast nephropathy risk
- Pulmonary risk factors
- Frailty indicators

Provide specific scores where possible and overall risk stratification.`,

  queryMode: `You are a clinical search assistant helping find information in patient data.
Be precise and quote exact values when found.
If data is not available, clearly state "Not documented" or "Not found".
Always cite where you found the information (e.g., "from problem list", "from medications").`
};

// Expose class globally for other scripts
window.ClinicalAnalyzer = class ClinicalAnalyzer {
  constructor(claudeAPI) {
    AnalyzerLogger.info('ClinicalAnalyzer constructor called');
    this.api = claudeAPI;
    AnalyzerLogger.info('API client set:', !!claudeAPI);
  }

  /**
   * Analyze antithrombotic medications and provide surgical recommendations
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Medication analysis with recommendations
   */
  async analyzeMedications(patientData) {
    AnalyzerLogger.analysis('analyzeMedications called');

    // Verify API is available
    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'medication_analysis',
        success: false,
        analysis: null,
        error: 'API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'medication_analysis',
        success: false,
        analysis: null,
        error: 'API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    const medications = patientData.medications || [];
    const problems = patientData.problems || [];
    AnalyzerLogger.info('Data counts:', { medications: medications.length, problems: problems.length });

    const prompt = `Analyze this patient's medications for vascular surgery planning:

CURRENT MEDICATIONS:
${JSON.stringify(medications, null, 2)}

ACTIVE PROBLEMS/DIAGNOSES:
${JSON.stringify(problems, null, 2)}

Provide:
1. List of antithrombotic medications with recommended hold times
2. Bridging recommendations if applicable
3. Reversal agents for emergency surgery
4. Any drug interactions of concern
5. Overall bleeding risk assessment

Format as a structured clinical summary.`;

    AnalyzerLogger.info('Sending medication analysis to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.medicationAnalysis,
        temperature: 0.2
      });

      AnalyzerLogger.info('Medication analysis result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'medication_analysis',
        success: result.success,
        analysis: result.content || null,
        error: result.error || null,
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('analyzeMedications exception:', e.message);
      return {
        type: 'medication_analysis',
        success: false,
        analysis: null,
        error: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Calculate perioperative risk scores
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Risk assessment
   */
  async assessRisk(patientData) {
    AnalyzerLogger.analysis('assessRisk() called');

    // Verify API is available
    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'risk_assessment',
        success: false,
        assessment: null,
        error: 'API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'risk_assessment',
        success: false,
        assessment: null,
        error: 'API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    const prompt = `Calculate perioperative risk for this vascular surgery patient:

DEMOGRAPHICS:
${JSON.stringify(patientData.patient || {}, null, 2)}

PROBLEMS/DIAGNOSES:
${JSON.stringify(patientData.problems || [], null, 2)}

MEDICATIONS:
${JSON.stringify(patientData.medications || [], null, 2)}

LABS (if available):
${JSON.stringify(patientData.labs || [], null, 2)}

VITALS:
${JSON.stringify(patientData.vitals || {}, null, 2)}

Calculate and provide:
1. RCRI Score (0-6) with component breakdown
2. Estimated cardiac risk percentage
3. Bleeding risk (low/moderate/high) with rationale
4. Contrast nephropathy risk if eGFR available
5. Overall surgical risk stratification
6. Recommendations for risk optimization`;

    AnalyzerLogger.info('Sending risk assessment to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.riskAssessment,
        temperature: 0.1
      });

      AnalyzerLogger.info('Risk assessment result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'risk_assessment',
        success: result.success,
        assessment: result.content || null,
        error: result.error || null,
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('assessRisk exception:', e.message);
      return {
        type: 'risk_assessment',
        success: false,
        assessment: null,
        error: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Generate a comprehensive pre-op summary
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Pre-op summary
   */
  async generatePreOpSummary(patientData) {
    AnalyzerLogger.analysis('generatePreOpSummary() called');

    // Verify API is available
    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'preop_summary',
        success: false,
        summary: null,
        error: 'API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'preop_summary',
        success: false,
        summary: null,
        error: 'API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    // Create a clean copy without raw data to avoid token limits
    const cleanData = {
      patientId: patientData.patientId,
      patient: patientData.patient,
      medications: patientData.medications || [],
      problems: patientData.problems || [],
      allergies: patientData.allergies || [],
      vitals: patientData.vitals,
      labs: patientData.labs,
      encounters: patientData.encounters
    };

    const prompt = `Generate a comprehensive vascular surgery pre-operative summary:

PATIENT DATA:
${JSON.stringify(cleanData, null, 2)}

Create a structured pre-op summary including:
1. Patient identification and demographics
2. Indication for surgery / presenting problem
3. Relevant vascular history
4. Key comorbidities
5. Current antithrombotic regimen with hold plan
6. Relevant labs (Cr, eGFR, INR, H/H)
7. Recent imaging findings (ABIs, duplex, CTA)
8. Allergies (especially contrast, latex, heparin)
9. Risk stratification summary
10. Outstanding items to address before surgery

Format for easy scanning by the surgical team.`;

    AnalyzerLogger.info('Sending pre-op summary to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.vascularExpert,
        maxTokens: 3000,
        temperature: 0.2
      });

      AnalyzerLogger.info('Pre-op summary result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'preop_summary',
        success: result.success,
        summary: result.content || null,
        error: result.error || null,
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('generatePreOpSummary exception:', e.message);
      return {
        type: 'preop_summary',
        success: false,
        summary: null,
        error: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Natural language query against patient data
   * @param {string} query - User's question
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Query response
   */
  async query(query, patientData) {
    AnalyzerLogger.analysis('query() called', { queryLength: query?.length || 0 });
    AnalyzerLogger.info('Patient data available:', {
      hasPatient: !!patientData?.patient,
      medications: patientData?.medications?.length || 0,
      problems: patientData?.problems?.length || 0
    });

    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'query_response',
        success: false,
        query: query,
        answer: 'Error: API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'query_response',
        success: false,
        query: query,
        answer: 'Error: API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    // Create a clean copy without raw data to avoid token limits
    const cleanData = {
      patientId: patientData.patientId,
      patient: patientData.patient,
      medications: patientData.medications || [],
      problems: patientData.problems || [],
      allergies: patientData.allergies || [],
      vitals: patientData.vitals,
      labs: patientData.labs,
      encounters: patientData.encounters
    };

    const prompt = `Answer this clinical question about the patient:

QUESTION: "${query}"

PATIENT DATA:
${JSON.stringify(cleanData, null, 2)}

Provide a direct, precise answer. If the information is not available in the data, say so clearly.`;

    AnalyzerLogger.info('Sending query to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.queryMode,
        temperature: 0.1
      });

      AnalyzerLogger.info('Query result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'query_response',
        success: result.success,
        query: query,
        answer: result.content || result.error || 'No response received',
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('query exception:', e.message);
      return {
        type: 'query_response',
        success: false,
        query: query,
        answer: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Identify critical alerts in patient data
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Critical alerts
   */
  async identifyAlerts(patientData) {
    AnalyzerLogger.analysis('identifyAlerts() called');
    AnalyzerLogger.info('Patient data for alerts:', {
      medications: patientData?.medications?.length || 0,
      problems: patientData?.problems?.length || 0,
      allergies: patientData?.allergies?.length || 0
    });

    // Verify API is available
    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'alerts',
        success: false,
        alerts: null,
        error: 'API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'alerts',
        success: false,
        alerts: null,
        error: 'API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    // Create a clean copy without raw data to avoid token limits
    const cleanData = {
      patientId: patientData.patientId,
      patient: patientData.patient,
      medications: patientData.medications || [],
      problems: patientData.problems || [],
      allergies: patientData.allergies || [],
      vitals: patientData.vitals,
      labs: patientData.labs
    };

    const prompt = `Review this patient data and identify any CRITICAL ALERTS for vascular surgery:

PATIENT DATA:
${JSON.stringify(cleanData, null, 2)}

Check for:
- Dual antiplatelet therapy or triple therapy
- Supratherapeutic INR or recent anticoagulant use
- Critical lab values (Cr >2, eGFR <30, Hgb <8, Plt <100)
- Contrast allergy with upcoming angiography
- Uncontrolled hypertension
- Recent MI or stroke (<6 weeks)
- Active infection
- Heparin allergy / HIT history
- Latex allergy

Format each alert as:
[PRIORITY: HIGH/MEDIUM] Alert Title
- Details
- Recommended action`;

    AnalyzerLogger.info('Sending alerts request to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.vascularExpert,
        temperature: 0.1
      });

      AnalyzerLogger.info('Alerts result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'alerts',
        success: result.success,
        alerts: result.content || null,
        error: result.error || null,
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('identifyAlerts exception:', e.message);
      return {
        type: 'alerts',
        success: false,
        alerts: null,
        error: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Extract and summarize imaging findings
   * @param {Object} patientData - Patient data from cache
   * @returns {Promise<Object>} - Imaging summary
   */
  async summarizeImaging(patientData) {
    AnalyzerLogger.analysis('summarizeImaging() called');

    // Verify API is available
    if (!this.api) {
      AnalyzerLogger.error('API client not set!');
      return {
        type: 'imaging_summary',
        success: false,
        summary: null,
        error: 'API client not initialized',
        timestamp: new Date().toISOString()
      };
    }

    if (!this.api.apiKey) {
      AnalyzerLogger.error('API key not configured!');
      return {
        type: 'imaging_summary',
        success: false,
        summary: null,
        error: 'API key not configured',
        timestamp: new Date().toISOString()
      };
    }

    // Create a clean copy without raw data to avoid token limits
    const cleanData = {
      patientId: patientData.patientId,
      patient: patientData.patient,
      problems: patientData.problems || [],
      labs: patientData.labs,
      encounters: patientData.encounters
    };

    const prompt = `Extract and summarize all vascular imaging findings from this patient data:

PATIENT DATA:
${JSON.stringify(cleanData, null, 2)}

Look for:
- ABIs (Ankle-Brachial Index) - quote exact values
- Arterial duplex results - stenosis percentages, velocities
- Venous duplex results - reflux, DVT findings
- CTA findings - aneurysm size, stenosis, occlusions
- MRA findings
- Angiogram results

Organize by:
1. Lower extremity arterial
2. Carotid
3. Aortic
4. Venous
5. Other

Include dates when available.`;

    AnalyzerLogger.info('Sending imaging summary to API...');

    try {
      const result = await this.api.sendMessage(prompt, {
        systemPrompt: SYSTEM_PROMPTS.vascularExpert,
        temperature: 0.1
      });

      AnalyzerLogger.info('Imaging summary result:', { success: result.success, hasContent: !!result.content, error: result.error });

      return {
        type: 'imaging_summary',
        success: result.success,
        summary: result.content || null,
        error: result.error || null,
        timestamp: new Date().toISOString()
      };
    } catch (e) {
      AnalyzerLogger.error('summarizeImaging exception:', e.message);
      return {
        type: 'imaging_summary',
        success: false,
        summary: null,
        error: `Exception: ${e.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ClinicalAnalyzer, SYSTEM_PROMPTS };
}

console.log('%c[Clinical Analyzer] ✅ clinical-analyzer.js LOADED SUCCESSFULLY', 'color: #10b981; font-weight: bold; font-size: 14px;');

} catch (e) {
  console.error('%c[Clinical Analyzer] ❌ clinical-analyzer.js FAILED TO LOAD:', 'color: #ef4444; font-weight: bold; font-size: 14px;', e.message);
  console.error(e);
}
