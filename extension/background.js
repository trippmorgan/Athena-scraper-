/**
 * Tier 1: The Transmitter
 * Manages the WebSocket connection to the Python Backend.
 * 
 * Responsibilities:
 * 1. Maintain persistent connection to ws://localhost:8000
 * 2. Receive JSON payloads from content.js
 * 3. Forward payloads to the Python Normalization Engine
 */

let socket = null;
const WS_URL = "ws://localhost:8000/ws/chrome";
let retryCount = 0;

/**
 * Enhanced Logging Helper
 * Uses CSS styling to make Shadow EHR logs distinct in the console.
 */
const Logger = {
  info: (msg, data = null) => {
    const time = new Date().toLocaleTimeString();
    console.log(`%c[Shadow EHR ${time}] ℹ️ ${msg}`, "color: #3b82f6; font-weight: bold;", data || '');
  },
  success: (msg, data = null) => {
    const time = new Date().toLocaleTimeString();
    console.log(`%c[Shadow EHR ${time}] ✅ ${msg}`, "color: #10b981; font-weight: bold;", data || '');
  },
  warn: (msg, data = null) => {
    const time = new Date().toLocaleTimeString();
    console.warn(`%c[Shadow EHR ${time}] ⚠️ ${msg}`, "color: #f59e0b; font-weight: bold;", data || '');
  },
  error: (msg, err = null) => {
    const time = new Date().toLocaleTimeString();
    console.error(`%c[Shadow EHR ${time}] ❌ ${msg}`, "color: #ef4444; font-weight: bold;", err || '');
  }
};

function connect() {
  Logger.info(`Attempting connection to ${WS_URL}... (Attempt ${retryCount + 1})`);
  
  try {
    socket = new WebSocket(WS_URL);
  } catch (e) {
    Logger.error("WebSocket instantiation failed", e);
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    Logger.success("WebSocket Connected Successfully");
    retryCount = 0; // Reset retry counter
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#10b981" }); // Emerald Green
  };

  socket.onclose = (event) => {
    Logger.warn(`WebSocket Disconnected (Code: ${event.code})`, event.reason);
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" }); // Red
    socket = null;
    scheduleReconnect();
  };

  socket.onerror = (err) => {
    Logger.error("Socket Error encountered", err);
  };
}

function scheduleReconnect() {
  const delay = Math.min(1000 * (2 ** retryCount), 30000); // Exponential backoff max 30s
  Logger.info(`Retrying connection in ${delay/1000} seconds...`);
  retryCount++;
  setTimeout(connect, delay);
}

// Initial connection
connect();

// Listen for messages from content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "RELAY_PAYLOAD") {
    
    const { url, method, payload: dataPayload } = message.data;
    const tabId = sender.tab ? sender.tab.id : 'unknown';

    // Check socket state
    if (socket && socket.readyState === WebSocket.OPEN) {
      
      // Create the payload matching backend/schemas.py: AthenaPayload
      const backendPayload = {
        endpoint: url,
        method: method,
        payload: dataPayload
      };

      try {
        const jsonStr = JSON.stringify(backendPayload);
        const payloadSize = (new TextEncoder().encode(jsonStr)).length;

        socket.send(jsonStr);
        
        // Log successful relay details
        const shortUrl = url.length > 80 ? url.substring(0, 80) + '...' : url;
        
        Logger.success(`Data Relayed from Tab ${tabId}`, {
          method,
          url: shortUrl,
          size: `${(payloadSize / 1024).toFixed(2)} KB`
        });
        
      } catch (e) {
        Logger.error("Failed to send payload over socket", e);
      }

    } else {
      const state = socket ? socket.readyState : 'NULL';
      const stateMap = { 0: 'CONNECTING', 1: 'OPEN', 2: 'CLOSING', 3: 'CLOSED' };
      const stateName = stateMap[state] || 'UNKNOWN';
      
      Logger.warn(`Dropped Packet - Socket not ready`, {
        state: stateName,
        url: url,
        tabId: tabId
      });
      
      // If closed and not reconnecting, trigger reconnect logic might be needed, 
      // though onclose usually handles it.
    }
  }
  
  // Return false as we don't need to send an async response to content.js
  return false; 
});