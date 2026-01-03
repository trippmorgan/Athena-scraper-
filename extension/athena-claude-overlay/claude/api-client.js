/**
 * Claude API Client for Athena AI Assistant
 * Handles all communication with the Anthropic API
 */

class ClaudeAPIClient {
  constructor() {
    this.apiKey = null;
    this.model = 'claude-sonnet-4-20250514';
    this.baseUrl = 'https://api.anthropic.com/v1/messages';
    this.initialized = false;
  }

  /**
   * Initialize the client with stored credentials
   */
  async init() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['anthropic_api_key', 'claude_model'], (result) => {
        this.apiKey = result.anthropic_api_key || null;
        this.model = result.claude_model || 'claude-sonnet-4-20250514';
        this.initialized = true;
        resolve(this.isConfigured());
      });
    });
  }

  /**
   * Check if API key is configured
   */
  isConfigured() {
    return this.apiKey && this.apiKey.startsWith('sk-ant-') && this.apiKey.length > 40;
  }

  /**
   * Update API key
   */
  setApiKey(key) {
    this.apiKey = key;
  }

  /**
   * Update model
   */
  setModel(model) {
    this.model = model;
  }

  /**
   * Send a message to Claude
   * @param {string} userMessage - The user's question or request
   * @param {object} context - Patient data context
   * @param {string} systemPrompt - Optional system prompt override
   * @returns {Promise<object>} - Claude's response
   */
  async sendMessage(userMessage, context = {}, systemPrompt = null) {
    if (!this.isConfigured()) {
      throw new Error('API key not configured. Please add your Anthropic API key in the extension settings.');
    }

    const system = systemPrompt || this.buildSystemPrompt(context);

    try {
      const response = await fetch(this.baseUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01'
        },
        body: JSON.stringify({
          model: this.model,
          max_tokens: 2048,
          system: system,
          messages: [
            { role: 'user', content: userMessage }
          ]
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error?.message || `API error: ${response.status}`);
      }

      const data = await response.json();
      return {
        success: true,
        content: data.content[0].text,
        model: data.model,
        usage: data.usage
      };

    } catch (error) {
      console.error('[Claude API] Error:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Build system prompt with patient context
   */
  buildSystemPrompt(context) {
    return `You are a clinical AI assistant for a vascular surgeon using the Athena EMR system. 
Your role is to provide helpful, accurate clinical analysis to support patient care decisions.

IMPORTANT GUIDELINES:
- Be concise and clinically focused
- Highlight safety concerns prominently (especially bleeding risk, drug interactions)
- Use standard medical terminology
- Always note when information is incomplete or uncertain
- For medication recommendations, include evidence level when known
- Never make up information - say "not available in data" if something is missing

PATIENT CONTEXT:
${this.formatPatientContext(context)}

When asked questions:
1. First address any immediate safety concerns
2. Provide the specific information requested
3. Note any relevant clinical considerations
4. Suggest follow-up if appropriate`;
  }

  /**
   * Format patient context for the system prompt
   */
  formatPatientContext(context) {
    if (!context || Object.keys(context).length === 0) {
      return 'No patient currently loaded.';
    }

    let formatted = '';

    if (context.demographics) {
      const d = context.demographics;
      formatted += `Patient: ${d.name || 'Unknown'}\n`;
      formatted += `MRN: ${d.mrn || 'Unknown'}\n`;
      formatted += `Age: ${d.age || 'Unknown'}\n`;
      formatted += `DOB: ${d.dob || 'Unknown'}\n`;
    }

    if (context.medications && context.medications.length > 0) {
      formatted += `\nActive Medications (${context.medications.length}):\n`;
      context.medications.forEach(med => {
        formatted += `- ${med.name}`;
        if (med.dose) formatted += ` ${med.dose}`;
        if (med.frequency) formatted += ` ${med.frequency}`;
        if (med.isAntithrombotic) formatted += ' [ANTITHROMBOTIC]';
        formatted += '\n';
      });
    }

    if (context.problems && context.problems.length > 0) {
      formatted += `\nActive Problems (${context.problems.length}):\n`;
      context.problems.forEach(prob => {
        formatted += `- ${prob.name}`;
        if (prob.icd10) formatted += ` (${prob.icd10})`;
        if (prob.isVascular) formatted += ' [VASCULAR]';
        formatted += '\n';
      });
    }

    if (context.allergies && context.allergies.length > 0) {
      formatted += `\nAllergies:\n`;
      context.allergies.forEach(allergy => {
        formatted += `- ${allergy.allergen}`;
        if (allergy.reaction) formatted += `: ${allergy.reaction}`;
        formatted += '\n';
      });
    }

    if (context.vitals) {
      formatted += `\nVitals:\n`;
      if (context.vitals.bp) formatted += `- BP: ${context.vitals.bp}\n`;
      if (context.vitals.hr) formatted += `- HR: ${context.vitals.hr}\n`;
      if (context.vitals.temp) formatted += `- Temp: ${context.vitals.temp}\n`;
    }

    if (context.labs && context.labs.length > 0) {
      formatted += `\nRecent Labs:\n`;
      context.labs.slice(0, 10).forEach(lab => {
        formatted += `- ${lab.name}: ${lab.value}`;
        if (lab.unit) formatted += ` ${lab.unit}`;
        if (lab.flag) formatted += ` [${lab.flag}]`;
        formatted += '\n';
      });
    }

    return formatted || 'No patient data available.';
  }

  /**
   * Analyze antithrombotic medications for surgical risk
   */
  async analyzeAntithrombotics(medications) {
    const prompt = `Analyze these medications for perioperative antithrombotic management:

${medications.map(m => `- ${m.name} ${m.dose || ''} ${m.frequency || ''}`).join('\n')}

Provide:
1. Classification of each antithrombotic (antiplatelet vs anticoagulant)
2. Recommended hold time before surgery
3. Reversal agents if applicable
4. Bridging recommendations if indicated
5. Restart timing post-procedure

Format as a structured clinical recommendation.`;

    return this.sendMessage(prompt, {}, this.buildAntithromboticSystemPrompt());
  }

  /**
   * Calculate surgical risk score
   */
  async calculateSurgicalRisk(patientData) {
    const prompt = `Based on this patient's clinical data, calculate their perioperative cardiac risk:

${this.formatPatientContext(patientData)}

Provide:
1. Revised Cardiac Risk Index (RCRI) score and components
2. Estimated MACE risk percentage
3. Recommendations for preoperative cardiac workup if indicated
4. Risk mitigation strategies

Format as a clinical risk assessment.`;

    return this.sendMessage(prompt);
  }

  /**
   * Generate surgical briefing
   */
  async generateSurgicalBriefing(patientData, procedureType = 'vascular') {
    const prompt = `Generate a pre-operative surgical briefing for this ${procedureType} surgery patient:

${this.formatPatientContext(patientData)}

Include:
1. Critical alerts (allergies, anticoagulation status, drug interactions)
2. Key comorbidities affecting surgical risk
3. Anesthesia considerations
4. Blood product/reversal agent needs
5. Post-op monitoring requirements

Keep it concise and actionable - this will be used for OR briefing.`;

    return this.sendMessage(prompt);
  }

  /**
   * Answer free-form clinical question
   */
  async askQuestion(question, patientData) {
    return this.sendMessage(question, patientData);
  }

  /**
   * Specialized system prompt for antithrombotic analysis
   */
  buildAntithromboticSystemPrompt() {
    return `You are a clinical pharmacology expert specializing in perioperative anticoagulation management.

Your recommendations should follow current guidelines:
- ACC/AHA Perioperative Guidelines
- CHEST Antithrombotic Therapy Guidelines
- STS/SCA Antiplatelet Management Guidelines

For each medication, know:
- Mechanism of action
- Half-life and time to clear
- Reversal agents
- Bridging protocols
- Bleeding risk vs thrombotic risk

Be specific with hold times (e.g., "Hold 5 days before surgery" not "several days").
Always consider the indication for the antithrombotic when recommending hold/bridge strategy.`;
  }

  /**
   * Stream response (for longer responses)
   * Note: Requires different API endpoint setup
   */
  async streamMessage(userMessage, context, onChunk) {
    // For now, use non-streaming
    // Streaming can be added later with SSE support
    const response = await this.sendMessage(userMessage, context);
    if (response.success) {
      onChunk(response.content);
    }
    return response;
  }
}

// Export singleton instance
const claudeAPI = new ClaudeAPIClient();

// Listen for credential updates from popup
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local') {
    if (changes.anthropic_api_key) {
      claudeAPI.setApiKey(changes.anthropic_api_key.newValue);
    }
    if (changes.claude_model) {
      claudeAPI.setModel(changes.claude_model.newValue);
    }
  }
});

// Initialize on load
claudeAPI.init();
