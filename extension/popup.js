// popup.js - Extension popup controller

const $ = id => document.getElementById(id);

function log(msg) {
  const logEl = $('log');
  const time = new Date().toLocaleTimeString('en-US', { hour12: false });
  logEl.textContent = `[${time}] ${msg}\n` + logEl.textContent;
}

function updateStatus(status) {
  // Backend connection
  const backendEl = $('backend-status');
  backendEl.textContent = status.connectionStatus || 'Unknown';
  backendEl.className = `status-value ${status.connectionStatus === 'connected' ? 'connected' : 'disconnected'}`;

  // Athena session
  const athenaEl = $('athena-status');
  const hasAthena = status.athenaTabs && status.athenaTabs.length > 0;
  athenaEl.textContent = hasAthena ? `Active (${status.athenaTabs.length} tab${status.athenaTabs.length > 1 ? 's' : ''})` : 'Not detected';
  athenaEl.className = `status-value ${hasAthena ? 'connected' : 'disconnected'}`;

  // Stats
  $('capture-count').textContent = status.captureCount || 0;
  $('active-count').textContent = status.activeFetchCount || 0;
  $('bytes-sent').textContent = Math.round((status.bytesSent || 0) / 1024);

  // Enable/disable buttons based on Athena session
  const buttons = ['btn-preop', 'btn-intraop', 'btn-postop'];
  buttons.forEach(id => {
    $(id).disabled = !hasAthena;
  });
}

async function refreshStatus() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'GET_STATUS' });
    updateStatus(response);
  } catch (e) {
    log('Error: ' + e.message);
  }
}

async function initiateActiveFetch(action) {
  const mrn = $('mrn-input').value.trim();
  if (!mrn) {
    log('Please enter an MRN');
    return;
  }

  log(`Initiating ${action} fetch for MRN: ${mrn}...`);
  $('mode-status').textContent = 'Active';
  $('mode-status').className = 'status-value active';

  try {
    const response = await chrome.runtime.sendMessage({
      type: 'INITIATE_ACTIVE_FETCH',
      action: action,
      payload: { mrn }
    });

    if (response.success) {
      log(`${action} fetch complete!`);
    } else {
      log(`Error: ${response.error}`);
    }
  } catch (e) {
    log('Error: ' + e.message);
  } finally {
    $('mode-status').textContent = 'Passive';
    $('mode-status').className = 'status-value';
    refreshStatus();
  }
}

// Event listeners
$('btn-preop').addEventListener('click', () => initiateActiveFetch('FETCH_PREOP'));
$('btn-intraop').addEventListener('click', () => initiateActiveFetch('FETCH_INTRAOP'));
$('btn-postop').addEventListener('click', () => initiateActiveFetch('FETCH_POSTOP'));

$('mrn-input').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    initiateActiveFetch('FETCH_PREOP');
  }
});

// Initial load
refreshStatus();
log('Popup initialized');

// Refresh status periodically
setInterval(refreshStatus, 2000);