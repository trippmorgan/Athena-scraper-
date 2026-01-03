/**
 * Athena AI Assistant - Popup Controller
 * Handles API key management, settings, and status display
 */

// ============================================================
// CONFIGURATION
// ============================================================

const CONFIG = {
  BACKEND_URL: 'http://localhost:8000',
  SCC_URL: 'http://localhost:8001',
  STORAGE_KEYS: {
    API_KEY: 'anthropic_api_key',
    MODEL: 'claude_model',
    SETTINGS: 'assistant_settings',
    STATS: 'session_stats'
  },
  DEFAULT_MODEL: 'claude-sonnet-4-20250514'
};

// ============================================================
// DOM ELEMENTS
// ============================================================

const elements = {
  // Status
  backendStatus: document.getElementById('backendStatus'),
  backendStatusText: document.getElementById('backendStatusText'),
  apiStatus: document.getElementById('apiStatus'),
  apiStatusText: document.getElementById('apiStatusText'),
  
  // API Key
  apiKeyInput: document.getElementById('apiKeyInput'),
  toggleVisibility: document.getElementById('toggleVisibility'),
  modelSelect: document.getElementById('modelSelect'),
  saveApiKey: document.getElementById('saveApiKey'),
  clearApiKey: document.getElementById('clearApiKey'),
  
  // Settings
  enableOverlay: document.getElementById('enableOverlay'),
  autoAnalyze: document.getElementById('autoAnalyze'),
  pushToScc: document.getElementById('pushToScc'),
  debugMode: document.getElementById('debugMode'),
  
  // Stats
  patientsViewed: document.getElementById('patientsViewed'),
  queriesMade: document.getElementById('queriesMade'),
  eventsCaptured: document.getElementById('eventsCaptured'),
  
  // Actions
  openOverlay: document.getElementById('openOverlay'),
  testConnection: document.getElementById('testConnection'),
  viewLogs: document.getElementById('viewLogs'),
  exportData: document.getElementById('exportData'),
  helpLink: document.getElementById('helpLink'),
  
  // Toast
  toast: document.getElementById('toast')
};

// ============================================================
// UTILITIES
// ============================================================

function showToast(message, type = 'info') {
  elements.toast.textContent = message;
  elements.toast.className = `toast show ${type}`;
  setTimeout(() => {
    elements.toast.classList.remove('show');
  }, 3000);
}

function maskApiKey(key) {
  if (!key || key.length < 20) return '';
  return key.substring(0, 12) + '...' + key.substring(key.length - 4);
}

function validateApiKey(key) {
  // Anthropic API keys start with sk-ant-
  return key && key.startsWith('sk-ant-') && key.length > 40;
}

// ============================================================
// STORAGE FUNCTIONS
// ============================================================

async function getStoredApiKey() {
  return new Promise((resolve) => {
    chrome.storage.local.get(CONFIG.STORAGE_KEYS.API_KEY, (result) => {
      resolve(result[CONFIG.STORAGE_KEYS.API_KEY] || '');
    });
  });
}

async function setStoredApiKey(key) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [CONFIG.STORAGE_KEYS.API_KEY]: key }, resolve);
  });
}

async function getStoredModel() {
  return new Promise((resolve) => {
    chrome.storage.local.get(CONFIG.STORAGE_KEYS.MODEL, (result) => {
      resolve(result[CONFIG.STORAGE_KEYS.MODEL] || CONFIG.DEFAULT_MODEL);
    });
  });
}

async function setStoredModel(model) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [CONFIG.STORAGE_KEYS.MODEL]: model }, resolve);
  });
}

async function getStoredSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(CONFIG.STORAGE_KEYS.SETTINGS, (result) => {
      resolve(result[CONFIG.STORAGE_KEYS.SETTINGS] || {
        enableOverlay: true,
        autoAnalyze: false,
        pushToScc: false,
        debugMode: false
      });
    });
  });
}

async function setStoredSettings(settings) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [CONFIG.STORAGE_KEYS.SETTINGS]: settings }, resolve);
  });
}

async function getStoredStats() {
  return new Promise((resolve) => {
    chrome.storage.local.get(CONFIG.STORAGE_KEYS.STATS, (result) => {
      resolve(result[CONFIG.STORAGE_KEYS.STATS] || {
        patientsViewed: 0,
        queriesMade: 0,
        eventsCaptured: 0
      });
    });
  });
}

// ============================================================
// STATUS CHECKS
// ============================================================

async function checkBackendStatus() {
  try {
    const response = await fetch(`${CONFIG.BACKEND_URL}/health`, {
      method: 'GET',
      timeout: 3000
    });
    
    if (response.ok) {
      elements.backendStatus.className = 'status-dot connected';
      elements.backendStatusText.textContent = 'Connected';
      return true;
    }
  } catch (error) {
    console.log('Backend not reachable:', error.message);
  }
  
  elements.backendStatus.className = 'status-dot disconnected';
  elements.backendStatusText.textContent = 'Offline';
  return false;
}

async function checkApiStatus() {
  const apiKey = await getStoredApiKey();
  
  if (!apiKey) {
    elements.apiStatus.className = 'status-dot warning';
    elements.apiStatusText.textContent = 'Not configured';
    return false;
  }
  
  if (!validateApiKey(apiKey)) {
    elements.apiStatus.className = 'status-dot disconnected';
    elements.apiStatusText.textContent = 'Invalid key';
    return false;
  }
  
  // Optionally test the API key with a minimal request
  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-3-5-haiku-20241022',
        max_tokens: 10,
        messages: [{ role: 'user', content: 'Hi' }]
      })
    });
    
    if (response.ok || response.status === 400) {
      // 400 might be returned for very short prompts, but means auth worked
      elements.apiStatus.className = 'status-dot connected';
      elements.apiStatusText.textContent = 'Valid';
      return true;
    } else if (response.status === 401) {
      elements.apiStatus.className = 'status-dot disconnected';
      elements.apiStatusText.textContent = 'Invalid key';
      return false;
    }
  } catch (error) {
    // Network error - assume key is valid but can't verify
    elements.apiStatus.className = 'status-dot warning';
    elements.apiStatusText.textContent = 'Saved (unverified)';
    return true;
  }
  
  elements.apiStatus.className = 'status-dot connected';
  elements.apiStatusText.textContent = 'Configured';
  return true;
}

// ============================================================
// UI INITIALIZATION
// ============================================================

async function initializeUI() {
  // Load API key (masked)
  const apiKey = await getStoredApiKey();
  if (apiKey) {
    elements.apiKeyInput.value = maskApiKey(apiKey);
    elements.apiKeyInput.dataset.hasKey = 'true';
  }
  
  // Load model selection
  const model = await getStoredModel();
  elements.modelSelect.value = model;
  
  // Load settings
  const settings = await getStoredSettings();
  elements.enableOverlay.checked = settings.enableOverlay;
  elements.autoAnalyze.checked = settings.autoAnalyze;
  elements.pushToScc.checked = settings.pushToScc;
  elements.debugMode.checked = settings.debugMode;
  
  // Load stats
  const stats = await getStoredStats();
  elements.patientsViewed.textContent = stats.patientsViewed;
  elements.queriesMade.textContent = stats.queriesMade;
  elements.eventsCaptured.textContent = stats.eventsCaptured;
  
  // Check connection status
  await checkBackendStatus();
  await checkApiStatus();
}

// ============================================================
// EVENT HANDLERS
// ============================================================

// Toggle API key visibility
elements.toggleVisibility.addEventListener('click', async () => {
  if (elements.apiKeyInput.type === 'password') {
    // Show actual key if we have one stored
    const apiKey = await getStoredApiKey();
    if (apiKey && elements.apiKeyInput.dataset.hasKey === 'true') {
      elements.apiKeyInput.value = apiKey;
    }
    elements.apiKeyInput.type = 'text';
    elements.toggleVisibility.textContent = '🔒';
  } else {
    elements.apiKeyInput.type = 'password';
    // Re-mask if showing stored key
    if (elements.apiKeyInput.dataset.hasKey === 'true') {
      const apiKey = await getStoredApiKey();
      elements.apiKeyInput.value = maskApiKey(apiKey);
    }
    elements.toggleVisibility.textContent = '👁';
  }
});

// Clear input when focused if showing masked key
elements.apiKeyInput.addEventListener('focus', () => {
  if (elements.apiKeyInput.dataset.hasKey === 'true' && 
      elements.apiKeyInput.value.includes('...')) {
    elements.apiKeyInput.value = '';
    elements.apiKeyInput.dataset.hasKey = 'false';
  }
});

// Validate key format on input
elements.apiKeyInput.addEventListener('input', () => {
  const key = elements.apiKeyInput.value;
  if (key.length === 0) {
    elements.apiKeyInput.classList.remove('valid', 'invalid');
  } else if (validateApiKey(key)) {
    elements.apiKeyInput.classList.remove('invalid');
    elements.apiKeyInput.classList.add('valid');
  } else if (key.length > 10) {
    elements.apiKeyInput.classList.remove('valid');
    elements.apiKeyInput.classList.add('invalid');
  }
});

// Save API key
elements.saveApiKey.addEventListener('click', async () => {
  const key = elements.apiKeyInput.value;
  
  if (!key || key.includes('...')) {
    showToast('Please enter an API key', 'error');
    return;
  }
  
  if (!validateApiKey(key)) {
    showToast('Invalid API key format (should start with sk-ant-)', 'error');
    return;
  }
  
  await setStoredApiKey(key);
  elements.apiKeyInput.dataset.hasKey = 'true';
  elements.apiKeyInput.type = 'password';
  elements.apiKeyInput.value = maskApiKey(key);
  elements.toggleVisibility.textContent = '👁';
  
  // Also save model
  await setStoredModel(elements.modelSelect.value);
  
  // Notify background script
  chrome.runtime.sendMessage({ 
    type: 'API_KEY_UPDATED',
    model: elements.modelSelect.value
  });
  
  showToast('API key saved successfully!', 'success');
  await checkApiStatus();
});

// Clear API key
elements.clearApiKey.addEventListener('click', async () => {
  await setStoredApiKey('');
  elements.apiKeyInput.value = '';
  elements.apiKeyInput.dataset.hasKey = 'false';
  elements.apiKeyInput.classList.remove('valid', 'invalid');
  
  chrome.runtime.sendMessage({ type: 'API_KEY_CLEARED' });
  
  showToast('API key cleared', 'info');
  await checkApiStatus();
});

// Model selection
elements.modelSelect.addEventListener('change', async () => {
  await setStoredModel(elements.modelSelect.value);
  chrome.runtime.sendMessage({ 
    type: 'MODEL_CHANGED',
    model: elements.modelSelect.value
  });
});

// Settings toggles
async function saveSettings() {
  const settings = {
    enableOverlay: elements.enableOverlay.checked,
    autoAnalyze: elements.autoAnalyze.checked,
    pushToScc: elements.pushToScc.checked,
    debugMode: elements.debugMode.checked
  };
  
  await setStoredSettings(settings);
  
  // Notify background script of settings change
  chrome.runtime.sendMessage({ 
    type: 'SETTINGS_UPDATED',
    settings
  });
}

elements.enableOverlay.addEventListener('change', saveSettings);
elements.autoAnalyze.addEventListener('change', saveSettings);
elements.pushToScc.addEventListener('change', saveSettings);
elements.debugMode.addEventListener('change', saveSettings);

// Quick Actions
elements.openOverlay.addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { type: 'TOGGLE_OVERLAY' });
      window.close();
    }
  });
});

elements.testConnection.addEventListener('click', async () => {
  elements.testConnection.disabled = true;
  elements.testConnection.querySelector('.action-title').textContent = 'Testing...';
  
  const backendOk = await checkBackendStatus();
  const apiOk = await checkApiStatus();
  
  elements.testConnection.disabled = false;
  elements.testConnection.querySelector('.action-title').textContent = 'Test Connection';
  
  if (backendOk && apiOk) {
    showToast('All connections OK!', 'success');
  } else if (!backendOk) {
    showToast('Backend not reachable - start the server', 'error');
  } else if (!apiOk) {
    showToast('API key issue - check your key', 'error');
  }
});

elements.viewLogs.addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        func: () => {
          console.log('%c[Athena AI] Opening DevTools - check Console tab', 
            'color: #4299e1; font-weight: bold;');
        }
      });
    }
  });
  showToast('Check DevTools Console (F12)', 'info');
});

elements.exportData.addEventListener('click', async () => {
  // Get all stored data
  chrome.storage.local.get(null, (data) => {
    // Remove sensitive data
    const exportData = { ...data };
    delete exportData[CONFIG.STORAGE_KEYS.API_KEY];
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    chrome.downloads.download({
      url: url,
      filename: `athena-assistant-export-${new Date().toISOString().slice(0,10)}.json`,
      saveAs: true
    });
    
    showToast('Export started', 'success');
  });
});

elements.helpLink.addEventListener('click', (e) => {
  e.preventDefault();
  chrome.tabs.create({ 
    url: 'https://github.com/trippmorgan/Athena-scraper-/wiki' 
  });
});

// ============================================================
// LISTEN FOR STAT UPDATES
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'STATS_UPDATED') {
    elements.patientsViewed.textContent = message.stats.patientsViewed;
    elements.queriesMade.textContent = message.stats.queriesMade;
    elements.eventsCaptured.textContent = message.stats.eventsCaptured;
  }
});

// ============================================================
// INITIALIZE
// ============================================================

document.addEventListener('DOMContentLoaded', initializeUI);
