/**
 * Overlay UI - Option B
 *
 * Floating assistant panel that appears in Athena.
 * Provides chat interface, alerts, and clinical analysis.
 */

// === EARLY LOAD LOGGING ===
console.log('%c[Overlay UI] 📦 overlay-ui.js LOADING...', 'color: #6366f1; font-weight: bold; font-size: 14px;');

try {
  // Logger for overlay debugging
const OverlayLogger = {
  _log: (level, emoji, msg, data) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Athena Overlay ${time}]`;
    const styles = {
      info: "color: #6366f1; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      ui: "color: #ec4899; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    data ? console.log(`%c${prefix} ${emoji} ${msg}`, style, data) : console.log(`%c${prefix} ${emoji} ${msg}`, style);
  },
  info: (msg, data) => OverlayLogger._log('info', 'ℹ️', msg, data),
  success: (msg, data) => OverlayLogger._log('success', '✅', msg, data),
  warn: (msg, data) => OverlayLogger._log('warn', '⚠️', msg, data),
  error: (msg, data) => OverlayLogger._log('error', '❌', msg, data),
  ui: (msg, data) => OverlayLogger._log('ui', '🎨', msg, data)
};

// Expose class globally for other scripts
window.AthenaOverlay = class AthenaOverlay {
  constructor() {
    this.isOpen = false;
    this.isMinimized = false;
    // Position lower on screen to avoid browser bar (was 20, now 100)
    this.position = { x: 20, y: 100 };
    this.container = null;
    this.chatHistory = [];
    this.currentPatientId = null;
    this.patientData = null;

    // Will be set by parent
    this.claudeAPI = null;
    this.clinicalAnalyzer = null;
  }

  /**
   * Initialize the overlay UI
   */
  init(claudeAPI, clinicalAnalyzer) {
    OverlayLogger.info('Initializing overlay UI...');
    OverlayLogger.info('claudeAPI provided:', !!claudeAPI);
    OverlayLogger.info('clinicalAnalyzer provided:', !!clinicalAnalyzer);

    this.claudeAPI = claudeAPI;
    this.clinicalAnalyzer = clinicalAnalyzer;

    try {
      this.createOverlay();
      OverlayLogger.success('Overlay DOM created');
    } catch (e) {
      OverlayLogger.error('Failed to create overlay DOM:', e.message);
      return;
    }

    try {
      this.setupEventListeners();
      OverlayLogger.success('Event listeners attached');
    } catch (e) {
      OverlayLogger.error('Failed to setup event listeners:', e.message);
    }

    OverlayLogger.success('Overlay initialization complete');
  }

  /**
   * Create the overlay DOM structure
   */
  createOverlay() {
    // Remove existing if present
    const existing = document.getElementById('athena-claude-overlay');
    if (existing) existing.remove();

    // Create container
    this.container = document.createElement('div');
    this.container.id = 'athena-claude-overlay';
    this.container.innerHTML = `
      <div class="aco-panel">
        <div class="aco-header" id="aco-header">
          <div class="aco-title">
            <span class="aco-icon">🤖</span>
            <span class="aco-title-text">Athena Assistant</span>
          </div>
          <div class="aco-controls">
            <button class="aco-btn" id="aco-minimize" title="Minimize">−</button>
            <button class="aco-btn" id="aco-close" title="Close">×</button>
          </div>
        </div>

        <div class="aco-body" id="aco-body">
          <!-- Quick Actions -->
          <div class="aco-quick-actions">
            <button class="aco-action-btn" data-action="alerts">
              <span>⚠️</span> Alerts
            </button>
            <button class="aco-action-btn" data-action="meds">
              <span>💊</span> Meds
            </button>
            <button class="aco-action-btn" data-action="risk">
              <span>📊</span> Risk
            </button>
            <button class="aco-action-btn" data-action="imaging">
              <span>🔬</span> Imaging
            </button>
            <button class="aco-action-btn" data-action="summary">
              <span>📋</span> Summary
            </button>
            <button class="aco-action-btn" data-action="debug" style="background: #7c3aed; color: white;">
              <span>🔧</span> Debug
            </button>
            <button class="aco-action-btn" data-action="refresh" style="background: #0ea5e9; color: white;">
              <span>🔄</span> Refresh
            </button>
          </div>

          <!-- Chat Messages -->
          <div class="aco-chat" id="aco-chat">
            <div class="aco-message aco-assistant">
              <div class="aco-message-content">
                Hello! I'm your Athena Assistant. I can help you:
                <ul>
                  <li>Analyze medications and bleeding risk</li>
                  <li>Calculate surgical risk scores</li>
                  <li>Summarize imaging findings</li>
                  <li>Answer questions about Athena or the patient</li>
                </ul>
                Click a quick action above or ask me anything!
              </div>
            </div>
          </div>

          <!-- Status Bar -->
          <div class="aco-status" id="aco-status">
            <span class="aco-status-dot"></span>
            <span class="aco-status-text">Ready</span>
          </div>

          <!-- Input Area -->
          <div class="aco-input-area">
            <textarea
              id="aco-input"
              class="aco-input"
              placeholder="Ask about this patient or Athena..."
              rows="2"
            ></textarea>
            <button id="aco-send" class="aco-send-btn">
              <span>Send</span>
            </button>
          </div>
        </div>

        <!-- Minimized State -->
        <div class="aco-minimized" id="aco-minimized" style="display: none;">
          <span class="aco-icon">🤖</span>
          <span class="aco-badge" id="aco-badge" style="display: none;">0</span>
        </div>
      </div>
    `;

    // Inject styles
    this.injectStyles();

    // Set initial position BEFORE appending
    this.container.style.position = 'fixed';
    this.container.style.left = `${this.position.x}px`;
    this.container.style.top = `${this.position.y}px`;

    // Add to page - start hidden
    this.container.style.display = 'none';
    document.body.appendChild(this.container);
    OverlayLogger.info('Overlay container appended to body (hidden by default)');

    // Restore position from storage
    this.restorePosition();
  }

  /**
   * Inject CSS styles
   */
  injectStyles() {
    if (document.getElementById('athena-claude-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'athena-claude-styles';
    styles.textContent = `
      #athena-claude-overlay {
        position: fixed;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 14px;
      }

      .aco-panel {
        width: 380px;
        max-height: 600px;
        background: #ffffff;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        border: 1px solid #e5e7eb;
      }

      .aco-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        cursor: move;
        user-select: none;
      }

      .aco-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
      }

      .aco-icon {
        font-size: 20px;
      }

      .aco-controls {
        display: flex;
        gap: 4px;
      }

      .aco-btn {
        width: 28px;
        height: 28px;
        border: none;
        background: rgba(255, 255, 255, 0.2);
        color: white;
        border-radius: 6px;
        cursor: pointer;
        font-size: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
      }

      .aco-btn:hover {
        background: rgba(255, 255, 255, 0.3);
      }

      .aco-body {
        display: flex;
        flex-direction: column;
        flex: 1;
        overflow: hidden;
      }

      .aco-quick-actions {
        display: flex;
        gap: 6px;
        padding: 12px;
        background: #f9fafb;
        border-bottom: 1px solid #e5e7eb;
        flex-wrap: wrap;
      }

      .aco-action-btn {
        padding: 6px 12px;
        border: 1px solid #d1d5db;
        background: white;
        border-radius: 20px;
        cursor: pointer;
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 4px;
        transition: all 0.2s;
      }

      .aco-action-btn:hover {
        background: #f3f4f6;
        border-color: #6366f1;
        color: #6366f1;
      }

      .aco-action-btn:active {
        transform: scale(0.95);
      }

      .aco-chat {
        flex: 1;
        overflow-y: auto;
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        min-height: 200px;
        max-height: 350px;
      }

      .aco-message {
        display: flex;
        gap: 8px;
        max-width: 95%;
      }

      .aco-message.aco-user {
        align-self: flex-end;
        flex-direction: row-reverse;
      }

      .aco-message-content {
        padding: 10px 14px;
        border-radius: 12px;
        line-height: 1.4;
      }

      .aco-assistant .aco-message-content {
        background: #f3f4f6;
        border-bottom-left-radius: 4px;
      }

      .aco-user .aco-message-content {
        background: #6366f1;
        color: white;
        border-bottom-right-radius: 4px;
      }

      .aco-message-content ul {
        margin: 8px 0 0 0;
        padding-left: 20px;
      }

      .aco-message-content li {
        margin: 4px 0;
      }

      .aco-message-content pre {
        background: #1f2937;
        color: #e5e7eb;
        padding: 8px;
        border-radius: 6px;
        overflow-x: auto;
        font-size: 12px;
        margin: 8px 0;
      }

      .aco-status {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 12px;
        background: #f9fafb;
        border-top: 1px solid #e5e7eb;
        font-size: 12px;
        color: #6b7280;
      }

      .aco-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #10b981;
      }

      .aco-status-dot.thinking {
        background: #f59e0b;
        animation: pulse 1s infinite;
      }

      .aco-status-dot.error {
        background: #ef4444;
      }

      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }

      .aco-input-area {
        display: flex;
        gap: 8px;
        padding: 12px;
        border-top: 1px solid #e5e7eb;
      }

      .aco-input {
        flex: 1;
        padding: 10px 12px;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        resize: none;
        font-family: inherit;
        font-size: 14px;
        outline: none;
        transition: border-color 0.2s;
      }

      .aco-input:focus {
        border-color: #6366f1;
      }

      .aco-send-btn {
        padding: 10px 16px;
        background: #6366f1;
        color: white;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 500;
        transition: background 0.2s;
      }

      .aco-send-btn:hover {
        background: #4f46e5;
      }

      .aco-send-btn:disabled {
        background: #9ca3af;
        cursor: not-allowed;
      }

      .aco-minimized {
        width: 50px;
        height: 50px;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        position: relative;
        transition: transform 0.2s;
      }

      .aco-minimized:hover {
        transform: scale(1.1);
      }

      .aco-badge {
        position: absolute;
        top: -4px;
        right: -4px;
        background: #ef4444;
        color: white;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 10px;
        min-width: 18px;
        text-align: center;
      }

      /* Alert styling in messages */
      .aco-alert-high {
        background: #fef2f2 !important;
        border-left: 3px solid #ef4444;
      }

      .aco-alert-medium {
        background: #fffbeb !important;
        border-left: 3px solid #f59e0b;
      }
    `;

    document.head.appendChild(styles);
  }

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    OverlayLogger.info('Setting up event listeners...');

    // Drag functionality
    const header = document.getElementById('aco-header');
    if (!header) {
      OverlayLogger.error('Header element not found!');
      // Don't return - continue setting up other listeners
    }

    let isDragging = false;
    let startX, startY;

    if (header) {
      header.addEventListener('mousedown', (e) => {
        // Only start drag if clicking on header itself, not buttons
        if (e.target.closest('.aco-btn')) return;
        isDragging = true;
        startX = e.clientX - this.position.x;
        startY = e.clientY - this.position.y;
        OverlayLogger.ui('Drag started', { x: this.position.x, y: this.position.y });
        e.preventDefault(); // Prevent text selection
      });
    }

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      this.position.x = e.clientX - startX;
      this.position.y = e.clientY - startY;
      this.updatePosition();
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        this.savePosition();
        OverlayLogger.ui('Drag ended', { x: this.position.x, y: this.position.y });
      }
    });

    // Minimize button
    const minimizeBtn = document.getElementById('aco-minimize');
    if (minimizeBtn) {
      minimizeBtn.addEventListener('click', () => {
        OverlayLogger.ui('Minimize button clicked');
        this.toggleMinimize();
      });
    }

    // Close button
    const closeBtn = document.getElementById('aco-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        OverlayLogger.ui('Close button clicked');
        this.hide();
      });
    }

    // Minimized state click
    const minimizedEl = document.getElementById('aco-minimized');
    if (minimizedEl) {
      minimizedEl.addEventListener('click', () => {
        OverlayLogger.ui('Minimized state clicked');
        this.toggleMinimize();
      });
    }

    // Send button
    const sendBtn = document.getElementById('aco-send');
    if (sendBtn) {
      sendBtn.addEventListener('click', () => {
        OverlayLogger.ui('Send button clicked');
        this.handleSend();
      });
    }

    // Enter to send
    const inputEl = document.getElementById('aco-input');
    if (inputEl) {
      inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          OverlayLogger.ui('Enter key pressed in input');
          this.handleSend();
        }
      });
    }

    // Quick action buttons
    const actionBtns = document.querySelectorAll('.aco-action-btn');
    OverlayLogger.info('Found quick action buttons:', actionBtns.length);

    actionBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = e.currentTarget.dataset.action;
        OverlayLogger.ui('Quick action clicked:', action);
        this.handleQuickAction(action);
      });
    });

    OverlayLogger.success('All event listeners attached');
  }

  /**
   * Update overlay position
   */
  updatePosition() {
    if (this.container) {
      this.container.style.left = `${this.position.x}px`;
      this.container.style.top = `${this.position.y}px`;
    }
  }

  /**
   * Save position to storage
   */
  async savePosition() {
    try {
      await chrome.storage.local.set({ overlayPosition: this.position });
    } catch (e) {
      // Ignore storage errors
    }
  }

  /**
   * Restore position from storage
   */
  async restorePosition() {
    try {
      const result = await chrome.storage.local.get(['overlayPosition']);
      if (result.overlayPosition) {
        this.position = result.overlayPosition;
        // Ensure Y is at least 80 to avoid browser bar
        if (this.position.y < 80) {
          this.position.y = 100;
          console.log('[Overlay UI] Adjusted Y position to avoid browser bar');
        }
      }
    } catch (e) {
      // Use default position
    }
    this.updatePosition();
  }

  /**
   * Toggle minimize state
   */
  toggleMinimize() {
    this.isMinimized = !this.isMinimized;
    console.log('%c[Overlay UI] 🔄 toggleMinimize() - now:', 'color: #ec4899; font-weight: bold;', this.isMinimized ? 'MINIMIZED (robot)' : 'EXPANDED');

    const body = document.getElementById('aco-body');
    const header = document.getElementById('aco-header');
    const minimized = document.getElementById('aco-minimized');
    const panel = this.container.querySelector('.aco-panel');

    if (this.isMinimized) {
      console.log('[Overlay UI] Switching to minimized state (🤖 robot icon)');
      body.style.display = 'none';
      header.style.display = 'none';
      minimized.style.display = 'flex';
      panel.style.width = 'auto';
      panel.style.boxShadow = 'none';
      panel.style.background = 'transparent';
      console.log('%c[Overlay UI] 🤖 Robot icon now visible', 'color: #10b981; font-weight: bold;');
    } else {
      console.log('[Overlay UI] Switching to expanded state (full panel)');
      body.style.display = 'flex';
      header.style.display = 'flex';
      minimized.style.display = 'none';
      panel.style.width = '380px';
      panel.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.2)';
      panel.style.background = '#ffffff';
      console.log('%c[Overlay UI] 📋 Full panel now visible', 'color: #10b981; font-weight: bold;');
    }
  }

  /**
   * Show the overlay
   */
  show() {
    console.log('%c[Overlay UI] 👁️ show() called', 'color: #10b981; font-weight: bold;');
    OverlayLogger.ui('show() called', { hasContainer: !!this.container, currentIsOpen: this.isOpen });

    if (this.container) {
      console.log('[Overlay UI] Container exists, setting display: block');
      console.log('[Overlay UI] Container parent:', this.container.parentElement?.tagName || 'NO PARENT');
      console.log('[Overlay UI] Container in DOM:', document.body.contains(this.container));

      this.container.style.display = 'block';
      this.isOpen = true;

      // Verify it's actually visible
      const rect = this.container.getBoundingClientRect();
      console.log('[Overlay UI] Container rect:', { x: rect.x, y: rect.y, width: rect.width, height: rect.height });
      console.log('%c[Overlay UI] ✅ Overlay shown', 'color: #10b981; font-weight: bold;');
      OverlayLogger.success('Overlay shown');
    } else {
      console.error('[Overlay UI] ❌ Cannot show - container is null!');
      OverlayLogger.error('Cannot show - container is null');
    }
  }

  /**
   * Hide the overlay
   */
  hide() {
    console.log('%c[Overlay UI] 🙈 hide() called', 'color: #f59e0b; font-weight: bold;');
    OverlayLogger.ui('hide() called', { hasContainer: !!this.container, currentIsOpen: this.isOpen });

    if (this.container) {
      this.container.style.display = 'none';
      this.isOpen = false;
      console.log('%c[Overlay UI] ✅ Overlay hidden', 'color: #f59e0b; font-weight: bold;');
      OverlayLogger.success('Overlay hidden');
    } else {
      console.error('[Overlay UI] ❌ Cannot hide - container is null!');
      OverlayLogger.error('Cannot hide - container is null');
    }
  }

  /**
   * Toggle overlay visibility
   */
  toggle() {
    console.log('%c[Overlay UI] 🔄 toggle() called', 'color: #ec4899; font-weight: bold;');
    console.log('[Overlay UI] Current state:', {
      isOpen: this.isOpen,
      hasContainer: !!this.container,
      containerDisplay: this.container?.style?.display || 'N/A'
    });
    OverlayLogger.ui('toggle() called', { currentIsOpen: this.isOpen });

    if (this.isOpen) {
      console.log('[Overlay UI] Was open, calling hide()...');
      this.hide();
    } else {
      console.log('[Overlay UI] Was closed, calling show()...');
      this.show();
    }
    console.log('[Overlay UI] After toggle, isOpen:', this.isOpen);
  }

  /**
   * Set patient data for context
   */
  setPatientData(patientId, data) {
    OverlayLogger.info('setPatientData called', {
      patientId,
      hasData: !!data,
      medications: data?.medications?.length || 0,
      problems: data?.problems?.length || 0,
      allergies: data?.allergies?.length || 0
    });
    this.currentPatientId = patientId;
    this.patientData = data;
    OverlayLogger.success('Patient data updated:', patientId);
  }

  /**
   * Add a message to the chat
   */
  addMessage(content, isUser = false, className = '') {
    const chat = document.getElementById('aco-chat');
    const message = document.createElement('div');
    message.className = `aco-message ${isUser ? 'aco-user' : 'aco-assistant'} ${className}`;
    message.innerHTML = `<div class="aco-message-content">${this.formatContent(content)}</div>`;
    chat.appendChild(message);
    chat.scrollTop = chat.scrollHeight;
  }

  /**
   * Format message content (markdown-like)
   */
  formatContent(content) {
    // Handle null/undefined content
    if (!content) {
      return '<em>No content received</em>';
    }

    // Ensure content is a string
    const text = String(content);

    // Basic formatting
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>')
      .replace(/• /g, '&bull; ');
  }

  /**
   * Set status
   */
  setStatus(text, state = 'ready') {
    const statusText = document.querySelector('.aco-status-text');
    const statusDot = document.querySelector('.aco-status-dot');

    statusText.textContent = text;
    statusDot.className = 'aco-status-dot';
    if (state === 'thinking') statusDot.classList.add('thinking');
    if (state === 'error') statusDot.classList.add('error');
  }

  /**
   * Handle send button click
   */
  async handleSend() {
    OverlayLogger.info('=== handleSend() START ===');

    const input = document.getElementById('aco-input');
    const sendBtn = document.getElementById('aco-send');

    OverlayLogger.info('Input element found:', !!input);
    OverlayLogger.info('Send button found:', !!sendBtn);

    if (!input) {
      OverlayLogger.error('Input element not found!');
      return;
    }

    const query = input.value.trim();
    OverlayLogger.info('Query text:', query || '(empty)');
    OverlayLogger.info('Query length:', query.length);

    if (!query) {
      OverlayLogger.warn('Empty query, ignoring');
      return;
    }

    // Add user message
    this.addMessage(query, true);
    input.value = '';

    // Disable input
    if (sendBtn) sendBtn.disabled = true;
    this.setStatus('Thinking...', 'thinking');

    try {
      // Check query type and route appropriately
      const isDebug = this.isDebugQuery(query);
      const isAthenaHelp = this.isAthenaHelpQuery(query);

      OverlayLogger.info('Query routing:', { isDebug, isAthenaHelp });

      if (isDebug) {
        // Route to code analysis
        OverlayLogger.info('Routing to code analysis...');
        const assistant = window.athenaAssistant;
        if (assistant) {
          await assistant.analyzeCode(query);
        } else {
          this.addMessage('Error: AthenaAssistant not available for code analysis');
        }
      } else if (isAthenaHelp) {
        OverlayLogger.info('Calling handleAthenaHelp...');
        await this.handleAthenaHelp(query);
      } else {
        OverlayLogger.info('Calling handlePatientQuery...');
        OverlayLogger.info('this.patientData exists:', !!this.patientData);
        OverlayLogger.info('this.clinicalAnalyzer exists:', !!this.clinicalAnalyzer);
        await this.handlePatientQuery(query);
      }
      OverlayLogger.success('=== handleSend() COMPLETE ===');
    } catch (error) {
      OverlayLogger.error('handleSend error:', error.message);
      OverlayLogger.error('Error stack:', error.stack);
      this.addMessage(`Error: ${error.message}`, false, 'aco-alert-high');
      this.setStatus('Error', 'error');
    }

    if (sendBtn) sendBtn.disabled = false;
  }

  /**
   * Check if query is about Athena usage
   */
  isAthenaHelpQuery(query) {
    const athenaKeywords = [
      'how do i', 'how to', 'where is', 'where can i',
      'athena', 'navigate', 'find the', 'order', 'schedule',
      'document', 'chart', 'screen'
    ];
    const lower = query.toLowerCase();
    return athenaKeywords.some(kw => lower.includes(kw)) &&
           !lower.includes('patient') && !lower.includes('medication');
  }

  /**
   * Check if query is a debug/extension question
   */
  isDebugQuery(query) {
    const debugKeywords = [
      'why is', 'not working', 'not loading', 'debug', 'extension',
      'fix', 'error', 'broken', 'issue', 'problem with',
      'data not', 'iframe', 'message', 'postmessage', 'overlay',
      'injector', 'interceptor', 'background', 'content script'
    ];
    const lower = query.toLowerCase();
    return debugKeywords.some(kw => lower.includes(kw)) &&
           (lower.includes('extension') || lower.includes('data') ||
            lower.includes('patient') || lower.includes('why'));
  }

  /**
   * Handle Athena help queries
   */
  async handleAthenaHelp(query) {
    OverlayLogger.info('=== handleAthenaHelp START ===');
    OverlayLogger.info('Query:', query);
    OverlayLogger.info('this.claudeAPI exists:', !!this.claudeAPI);

    if (!this.claudeAPI) {
      OverlayLogger.error('claudeAPI is not set!');
      throw new Error('Claude API not initialized');
    }

    // Check if API key is configured
    if (!this.claudeAPI.apiKey) {
      OverlayLogger.error('No API key configured!');
      this.addMessage(
        '⚠️ **API Key Required**\n\n' +
        'Please configure your Claude API key:\n' +
        '1. Click the extension icon in your browser\n' +
        '2. Enter your API key (starts with sk-ant-)\n' +
        '3. Click "Save Key"\n\n' +
        'Get an API key at: console.anthropic.com'
      );
      this.setStatus('API key required', 'error');
      return;
    }

    const systemPrompt = `You are an Athena EMR expert assistant. Help users navigate and use Athena efficiently.

If you don't know the exact steps, provide general guidance and suggest checking Athena's help documentation.
Be concise and provide step-by-step instructions when possible.`;

    OverlayLogger.info('Sending to Claude API...');

    try {
      const result = await this.claudeAPI.sendMessage(query, {
        systemPrompt,
        temperature: 0.3
      });

      OverlayLogger.info('Claude API result:', {
        success: result.success,
        hasContent: !!result.content,
        contentLength: result.content?.length || 0,
        error: result.error
      });

      if (result.success) {
        this.addMessage(result.content);
        this.setStatus('Ready');
        OverlayLogger.success('=== handleAthenaHelp COMPLETE ===');
      } else {
        throw new Error(result.error);
      }
    } catch (e) {
      OverlayLogger.error('claudeAPI.sendMessage threw:', e.message);
      throw e;
    }
  }

  /**
   * Handle patient-related queries
   */
  async handlePatientQuery(query) {
    OverlayLogger.info('=== handlePatientQuery START ===');
    OverlayLogger.info('Query:', query);
    OverlayLogger.info('this.patientData:', this.patientData ? 'exists' : 'NULL');

    if (this.patientData) {
      OverlayLogger.info('Patient data contents:', {
        patientId: this.patientData.patientId,
        medications: this.patientData.medications?.length || 0,
        problems: this.patientData.problems?.length || 0,
        allergies: this.patientData.allergies?.length || 0,
        hasRaw: !!this.patientData.raw
      });
    }

    // Check if API key is configured first
    if (!this.claudeAPI?.apiKey) {
      OverlayLogger.error('No API key configured!');
      this.addMessage(
        '⚠️ **API Key Required**\n\n' +
        'Please configure your Claude API key:\n' +
        '1. Click the extension icon in your browser\n' +
        '2. Enter your API key (starts with sk-ant-)\n' +
        '3. Click "Save Key"\n\n' +
        'Get an API key at: console.anthropic.com'
      );
      this.setStatus('API key required', 'error');
      return;
    }

    if (!this.patientData) {
      OverlayLogger.warn('No patient data loaded - showing message to user');
      this.addMessage('No patient data loaded. Please navigate to a patient in Athena first, or click one of the quick action buttons after the page loads some data.');
      this.setStatus('Ready');
      return;
    }

    if (!this.clinicalAnalyzer) {
      OverlayLogger.error('clinicalAnalyzer is not set!');
      throw new Error('Clinical Analyzer not initialized');
    }

    OverlayLogger.info('clinicalAnalyzer exists, calling query()...');

    try {
      const result = await this.clinicalAnalyzer.query(query, this.patientData);
      OverlayLogger.info('Analyzer result:', {
        success: result.success,
        hasAnswer: !!result.answer,
        answerLength: result.answer?.length || 0,
        error: result.error
      });

      if (result.success) {
        this.addMessage(result.answer);
        this.setStatus('Ready');
        OverlayLogger.success('=== handlePatientQuery COMPLETE ===');
      } else {
        OverlayLogger.error('Query failed:', result.error || result.answer);
        throw new Error(result.error || 'Failed to analyze query');
      }
    } catch (e) {
      OverlayLogger.error('clinicalAnalyzer.query threw:', e.message);
      throw e;
    }
  }

  /**
   * Handle quick action buttons
   */
  async handleQuickAction(action) {
    OverlayLogger.info('handleQuickAction called:', action);

    // Debug action doesn't require patient data or API key initially
    if (action === 'debug') {
      return this.handleDebugAction();
    }

    // Refresh action - request fresh data from all frames
    if (action === 'refresh') {
      return this.handleRefreshAction();
    }

    // Check API key first
    if (!this.claudeAPI?.apiKey) {
      OverlayLogger.error('No API key for quick action!');
      this.addMessage(
        '⚠️ **API Key Required**\n\n' +
        'Please configure your Claude API key first.\n' +
        'Click the extension icon and enter your key.'
      );
      this.setStatus('API key required', 'error');
      return;
    }

    // Try to merge with interceptor data before checking
    this.mergeWithInterceptorData();

    if (!this.patientData) {
      OverlayLogger.warn('No patient data for quick action');
      this.addMessage('No patient data loaded. Please navigate to a patient in Athena first. Data is captured automatically as the page loads.');
      return;
    }

    if (!this.clinicalAnalyzer) {
      OverlayLogger.error('clinicalAnalyzer not set for quick action!');
      this.addMessage('Error: Clinical analyzer not initialized');
      return;
    }

    this.setStatus('Analyzing...', 'thinking');

    try {
      let result;

      switch (action) {
        case 'alerts':
          this.addMessage('Checking for critical alerts...', true);
          OverlayLogger.info('Calling identifyAlerts...');
          result = await this.clinicalAnalyzer.identifyAlerts(this.patientData);
          OverlayLogger.info('identifyAlerts result:', { success: result?.success, hasAlerts: !!result?.alerts });
          this.addMessage(result?.alerts || result?.error || 'No alerts data received');
          break;

        case 'meds':
          this.addMessage('Analyzing medications...', true);
          OverlayLogger.info('Calling analyzeMedications...');
          result = await this.clinicalAnalyzer.analyzeMedications(this.patientData);
          OverlayLogger.info('analyzeMedications result:', { success: result?.success, hasAnalysis: !!result?.analysis });
          this.addMessage(result?.analysis || result?.error || 'No medication analysis received');
          break;

        case 'risk':
          this.addMessage('Calculating risk scores...', true);
          OverlayLogger.info('Calling assessRisk...');
          result = await this.clinicalAnalyzer.assessRisk(this.patientData);
          OverlayLogger.info('assessRisk result:', { success: result?.success, hasAssessment: !!result?.assessment });
          this.addMessage(result?.assessment || result?.error || 'No risk assessment received');
          break;

        case 'imaging':
          this.addMessage('Summarizing imaging findings...', true);
          OverlayLogger.info('Calling summarizeImaging...');
          result = await this.clinicalAnalyzer.summarizeImaging(this.patientData);
          OverlayLogger.info('summarizeImaging result:', { success: result?.success, hasSummary: !!result?.summary });
          this.addMessage(result?.summary || result?.error || 'No imaging summary received');
          break;

        case 'summary':
          this.addMessage('Generating pre-op summary...', true);
          OverlayLogger.info('Calling generatePreOpSummary...');
          result = await this.clinicalAnalyzer.generatePreOpSummary(this.patientData);
          OverlayLogger.info('generatePreOpSummary result:', { success: result?.success, hasSummary: !!result?.summary });
          this.addMessage(result?.summary || result?.error || 'No pre-op summary received');
          break;

        default:
          OverlayLogger.warn('Unknown action:', action);
      }

      this.setStatus('Ready');
      OverlayLogger.success('Quick action completed:', action);

    } catch (error) {
      OverlayLogger.error('Quick action error:', error.message);
      this.addMessage(`Error: ${error.message}`, false, 'aco-alert-high');
      this.setStatus('Error', 'error');
    }
  }

  /**
   * Handle debug action - examine extension state and code
   */
  async handleDebugAction() {
    OverlayLogger.info('Debug action triggered');

    this.addMessage('🔧 **Debug Mode**\n\nRunning diagnostics...', true);
    this.setStatus('Debugging...', 'thinking');

    try {
      // Get athenaAssistant instance for debug functions
      const assistant = window.athenaAssistant;
      if (!assistant) {
        this.addMessage('Error: AthenaAssistant not found');
        return;
      }

      // Run diagnostics
      const diagResult = await assistant.diagnose();

      // Build debug report
      let report = '**🔍 Extension Diagnostic Report**\n\n';
      report += `**Initialized:** ${diagResult.initialized ? '✅ Yes' : '❌ No'}\n`;
      report += `**API Client:** ${diagResult.hasApi ? '✅ Ready' : '❌ Missing'}\n`;
      report += `**API Key:** ${diagResult.hasApiKey ? '✅ Configured' : '⚠️ Not set'}\n`;
      report += `**Overlay:** ${diagResult.hasOverlay ? '✅ Active' : '❌ Missing'}\n`;
      report += `**Patient Data:** ${diagResult.hasPatientData ? '✅ Loaded' : '⚠️ None'}\n`;
      report += `**Overlay Open:** ${diagResult.overlayOpen ? 'Yes' : 'No'}\n\n`;

      // Add patient data info if available
      if (this.patientData) {
        report += '**Patient Context:**\n';
        report += `• ID: ${this.currentPatientId || 'Unknown'}\n`;
        report += `• Medications: ${this.patientData.medications?.length || 0}\n`;
        report += `• Problems: ${this.patientData.problems?.length || 0}\n`;
        report += `• Allergies: ${this.patientData.allergies?.length || 0}\n`;
        report += `• Raw captures: ${this.patientData.raw?.length || 0}\n\n`;
      }

      // Check interceptor storage
      const interceptorData = this.getInterceptorPatientData();
      if (interceptorData) {
        report += '**Interceptor Storage:**\n';
        report += `• Patient ID: ${interceptorData.patientId}\n`;
        report += `• Medications: ${interceptorData.medications?.length || 0}\n`;
        report += `• Problems: ${interceptorData.problems?.length || 0}\n`;
        report += `• Allergies: ${interceptorData.allergies?.length || 0}\n`;
        report += `• Raw captures: ${interceptorData.raw?.length || 0}\n\n`;
      } else {
        report += '**Interceptor Storage:** No data captured yet\n\n';
      }

      // Add console commands
      report += '**Debug Commands (run in console):**\n';
      report += '`window.athenaAssistant.diagnose()` - Full diagnostic\n';
      report += '`window.athenaAssistant.debugCode()` - Load extension code\n';
      report += '`window.athenaAssistant.analyzeCode("your question")` - AI code analysis\n';
      report += '`window.__shadowEhrPatientCache.getData()` - View cached data\n';
      report += '`window.__athenaPatientData` - View interceptor storage\n';

      this.addMessage(report);

      // If API key is set, offer to run AI analysis
      if (diagResult.hasApiKey) {
        this.addMessage('💡 **Tip:** Type a debug question like "Why is patient data not loading?" and I\'ll analyze the extension code to find the issue.');
      }

      this.setStatus('Ready');

    } catch (error) {
      OverlayLogger.error('Debug action error:', error.message);
      this.addMessage(`Debug error: ${error.message}`, false, 'aco-alert-high');
      this.setStatus('Error', 'error');
    }
  }

  /**
   * Get patient data from interceptor's window storage
   * This is a fallback method that accesses data stored directly by interceptor.js
   */
  getInterceptorPatientData() {
    // Check if interceptor has stored data
    if (window.__athenaPatientData) {
      const patients = Object.entries(window.__athenaPatientData);
      if (patients.length > 0) {
        // Get most recent patient data
        patients.sort((a, b) => new Date(b[1].lastUpdated) - new Date(a[1].lastUpdated));
        const [patientId, data] = patients[0];
        OverlayLogger.info('Got patient data from interceptor storage:', {
          patientId,
          medications: data.medications?.length || 0,
          problems: data.problems?.length || 0,
          allergies: data.allergies?.length || 0
        });
        return { patientId, ...data };
      }
    }
    return null;
  }

  /**
   * Merge interceptor data with current patient data
   * Interceptor data may have more complete extraction
   */
  mergeWithInterceptorData() {
    const interceptorData = this.getInterceptorPatientData();
    if (!interceptorData) return false;

    const patientId = interceptorData.patientId;

    // If we don't have any data, use interceptor data
    if (!this.patientData || !this.currentPatientId) {
      this.currentPatientId = patientId;
      this.patientData = interceptorData;
      OverlayLogger.success('Using interceptor data as primary source');
      return true;
    }

    // If same patient, merge in any missing data
    if (this.currentPatientId === patientId) {
      // Prefer interceptor data for arrays if our data is empty
      if (!this.patientData.medications?.length && interceptorData.medications?.length) {
        this.patientData.medications = interceptorData.medications;
        OverlayLogger.info('Merged medications from interceptor');
      }
      if (!this.patientData.problems?.length && interceptorData.problems?.length) {
        this.patientData.problems = interceptorData.problems;
        OverlayLogger.info('Merged problems from interceptor');
      }
      if (!this.patientData.allergies?.length && interceptorData.allergies?.length) {
        this.patientData.allergies = interceptorData.allergies;
        OverlayLogger.info('Merged allergies from interceptor');
      }
      return true;
    }

    return false;
  }

  /**
   * Handle refresh action - request cached data from all iframes
   */
  async handleRefreshAction() {
    OverlayLogger.info('Refresh action triggered');

    this.addMessage('🔄 **Refreshing patient data...**', true);
    this.setStatus('Refreshing...', 'thinking');

    try {
      const assistant = window.athenaAssistant;
      if (assistant && typeof assistant.requestCachedDataFromFrames === 'function') {
        // Request data from all frames
        assistant.requestCachedDataFromFrames();

        // Wait a moment for responses
        await new Promise(resolve => setTimeout(resolve, 1500));
      }

      // Also try to merge with interceptor data (fallback)
      this.mergeWithInterceptorData();

      // Check if we got data
      if (this.patientData) {
        let report = '**✅ Data Refreshed**\n\n';
        report += `**Patient ID:** ${this.currentPatientId || 'Unknown'}\n`;
        report += `**Medications:** ${this.patientData.medications?.length || 0}\n`;
        report += `**Problems:** ${this.patientData.problems?.length || 0}\n`;
        report += `**Allergies:** ${this.patientData.allergies?.length || 0}\n`;
        report += `**Raw Captures:** ${this.patientData.raw?.length || 0}\n\n`;
        report += '_Data is collected passively as you browse. Navigate to different sections in Athena to capture more data._';
        this.addMessage(report);
      } else {
        // Final fallback - check current cache
        const cache = window.__shadowEhrPatientCache;
        if (cache) {
          const data = cache.getData();
          if (data?.patientId) {
            this.setPatientData(data.patientId, data);
            this.addMessage(`✅ Found cached data for patient ${data.patientId}`);
          } else {
            this.addMessage(
              '⚠️ **No patient data found**\n\n' +
              'Patient data is captured passively as Athena loads. Try:\n' +
              '• Navigate to a patient chart\n' +
              '• Click on medications, problems, or allergies tabs\n' +
              '• Refresh the Athena page\n\n' +
              '_Data flows automatically - no manual fetch needed._'
            );
          }
        } else {
          this.addMessage('Patient data cache not available.');
        }
      }

      this.setStatus('Ready');

    } catch (error) {
      OverlayLogger.error('Refresh action error:', error.message);
      this.addMessage(`Refresh error: ${error.message}`, false, 'aco-alert-high');
      this.setStatus('Error', 'error');
    }
  }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AthenaOverlay };
}

console.log('%c[Overlay UI] ✅ overlay-ui.js LOADED SUCCESSFULLY', 'color: #10b981; font-weight: bold; font-size: 14px;');

} catch (e) {
  console.error('%c[Overlay UI] ❌ overlay-ui.js FAILED TO LOAD:', 'color: #ef4444; font-weight: bold; font-size: 14px;', e.message);
  console.error(e);
}
