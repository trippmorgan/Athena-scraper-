/**
 * Claude API Client for Chrome Extension
 *
 * Handles all communication with Anthropic's Claude API.
 * Supports streaming responses for real-time UI updates.
 */

// === EARLY LOAD LOGGING ===
console.log('%c[Claude API] 📦 api-client.js LOADING...', 'color: #0ea5e9; font-weight: bold; font-size: 14px;');

try {
  // Logger for API debugging
const APILogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Claude API ${time}]`;
    const styles = {
      info: "color: #0ea5e9; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      api: "color: #a855f7; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => APILogger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => APILogger._log('success', '✅', msg, data),
  warn: (msg, data) => APILogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => APILogger._log('error', '❌', msg, data),
  api: (msg, data) => APILogger._log('api', '🔌', msg, data)
};

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

// Default model - can be overridden per request
const DEFAULT_MODEL = 'claude-sonnet-4-20250514';

// Expose class globally for other scripts
window.ClaudeAPIClient = class ClaudeAPIClient {
  constructor(apiKey = null) {
    APILogger.info('ClaudeAPIClient constructor called');
    // API key can be set via constructor, storage, or environment
    this.apiKey = apiKey;
    this.model = DEFAULT_MODEL;
    this.maxTokens = 2048;

    // Load API key from storage if not provided
    if (!this.apiKey) {
      APILogger.info('No API key provided, loading from storage...');
      this._loadApiKey();
    } else {
      APILogger.success('API key provided in constructor');
    }
  }

  async _loadApiKey() {
    try {
      APILogger.info('Loading API key from storage...');
      const result = await chrome.storage.local.get(['anthropicApiKey']);
      if (result.anthropicApiKey) {
        this.apiKey = result.anthropicApiKey;
        APILogger.success('API key loaded from storage', { keyPrefix: this.apiKey.substring(0, 12) + '...' });
      } else {
        APILogger.warn('No API key found in storage - configure in extension popup');
      }
    } catch (e) {
      APILogger.error('Could not load API key from storage:', e.message);
    }
  }

  /**
   * Ensure API key is loaded (call before first use if needed)
   */
  async ensureApiKey() {
    if (!this.apiKey) {
      await this._loadApiKey();
    }
    return !!this.apiKey;
  }

  async setApiKey(apiKey) {
    APILogger.info('setApiKey called');
    this.apiKey = apiKey;
    try {
      await chrome.storage.local.set({ anthropicApiKey: apiKey });
      APILogger.success('API key saved to storage');
    } catch (e) {
      APILogger.error('Could not save API key:', e.message);
    }
  }

  /**
   * Send a message to Claude and get a response
   * @param {string} prompt - The user's prompt
   * @param {Object} options - Additional options
   * @param {string} options.systemPrompt - System prompt for context
   * @param {Array} options.messages - Conversation history
   * @param {string} options.model - Model to use
   * @param {number} options.maxTokens - Max tokens in response
   * @returns {Promise<Object>} - Claude's response
   */
  async sendMessage(prompt, options = {}) {
    APILogger.api('sendMessage called', { promptLength: prompt?.length || 0 });

    if (!this.apiKey) {
      APILogger.error('No API key configured!');
      return {
        success: false,
        error: 'Claude API key not configured. Please set your API key in extension settings.',
        content: null
      };
    }

    const {
      systemPrompt = null,
      messages = [],
      model = this.model,
      maxTokens = this.maxTokens,
      temperature = 0.3
    } = options;

    APILogger.info('Request config:', { model, maxTokens, temperature, hasSystemPrompt: !!systemPrompt });

    // Build messages array
    const apiMessages = [
      ...messages,
      { role: 'user', content: prompt }
    ];

    const requestBody = {
      model,
      max_tokens: maxTokens,
      messages: apiMessages,
      temperature
    };

    // Add system prompt if provided
    if (systemPrompt) {
      requestBody.system = systemPrompt;
    }

    APILogger.api('Sending request via background worker...', { model });

    // Route through background worker for reliable cross-origin requests
    // Content scripts can have issues with direct fetch to external APIs
    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          {
            type: 'CLAUDE_API_REQUEST',
            payload: {
              apiKey: this.apiKey,
              messages: apiMessages,
              systemPrompt,
              model,
              temperature,
              maxTokens
            }
          },
          (response) => {
            if (chrome.runtime.lastError) {
              APILogger.error('Message send failed:', chrome.runtime.lastError.message);
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }

            APILogger.info('Response from background:', {
              success: response?.success,
              hasContent: !!response?.content,
              error: response?.error
            });

            resolve(response);
          }
        );
      });

      if (result.success) {
        APILogger.success('Response received:', {
          inputTokens: result.usage?.input_tokens,
          outputTokens: result.usage?.output_tokens,
          contentLength: result.content?.length || 0
        });
      }

      return result;

    } catch (error) {
      APILogger.error('Request failed:', error.message);
      return {
        success: false,
        error: error.message,
        content: null
      };
    }
  }

  /**
   * Stream a response from Claude for real-time display
   * @param {string} prompt - The user's prompt
   * @param {Function} onChunk - Callback for each text chunk
   * @param {Object} options - Additional options
   * @returns {Promise<Object>} - Final response summary
   */
  async streamMessage(prompt, onChunk, options = {}) {
    if (!this.apiKey) {
      throw new Error('Claude API key not configured.');
    }

    const {
      systemPrompt = null,
      messages = [],
      model = this.model,
      maxTokens = this.maxTokens,
      temperature = 0.3
    } = options;

    const apiMessages = [
      ...messages,
      { role: 'user', content: prompt }
    ];

    const requestBody = {
      model,
      max_tokens: maxTokens,
      messages: apiMessages,
      temperature,
      stream: true
    };

    if (systemPrompt) {
      requestBody.system = systemPrompt;
    }

    try {
      const response = await fetch(ANTHROPIC_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': ANTHROPIC_VERSION
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        throw new Error(`Claude API error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'content_block_delta' && data.delta?.text) {
                fullText += data.delta.text;
                onChunk(data.delta.text);
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }

      return {
        success: true,
        content: fullText
      };

    } catch (error) {
      console.error('[Claude API] Stream failed:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Check if API is configured and working
   * @returns {Promise<boolean>}
   */
  async healthCheck() {
    APILogger.info('healthCheck called');

    if (!this.apiKey) {
      APILogger.warn('Health check failed - no API key');
      return { healthy: false, reason: 'No API key configured' };
    }

    try {
      APILogger.info('Sending health check via background worker...');

      const result = await new Promise((resolve) => {
        chrome.runtime.sendMessage(
          { type: 'CLAUDE_HEALTH_CHECK', apiKey: this.apiKey },
          (response) => {
            if (chrome.runtime.lastError) {
              resolve({ success: false, error: chrome.runtime.lastError.message });
            } else {
              resolve(response || { success: false, error: 'No response' });
            }
          }
        );
      });

      const status = {
        healthy: result.success,
        reason: result.success ? 'API responding' : (result.error || 'Unknown error')
      };
      APILogger.info('Health check result:', status);
      return status;
    } catch (e) {
      APILogger.error('Health check failed:', e.message);
      return { healthy: false, reason: e.message };
    }
  }
}

// Export singleton instance
const claudeAPI = new ClaudeAPIClient();

// Also export class for custom instances
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ClaudeAPIClient, claudeAPI };
}

console.log('%c[Claude API] ✅ api-client.js LOADED SUCCESSFULLY', 'color: #10b981; font-weight: bold; font-size: 14px;');

} catch (e) {
  console.error('%c[Claude API] ❌ api-client.js FAILED TO LOAD:', 'color: #ef4444; font-weight: bold; font-size: 14px;', e.message);
  console.error(e);
}
