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

/**
 * Helper for styled logs
 */
function log(msg, data = null) {
  const time = new Date().toLocaleTimeString();
  const style = "color: #00a3cc; font-weight: bold;";
  if (data) {
    console.log(`%c[Shadow EHR ${time}] ${msg}`, style, data);
  } else {
    console.log(`%c[Shadow EHR ${time}] ${msg}`, style);
  }
}

function connect() {
  log(`Attempting connection to ${WS_URL}...`);
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    log("✅ WebSocket Connected Successfully");
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#10b981" }); // Emerald Green
  };

  socket.onclose = (event) => {
    log(`❌ WebSocket Disconnected (Code: ${event.code})`, event.reason);
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#ef4444" }); // Red
    socket = null;
    log("Retrying connection in 5 seconds...");
    setTimeout(connect, 5000);
  };

  socket.onerror = (err) => {
    // console.error prints raw red text, good for actual errors
    console.error("[Shadow EHR] Socket Error:", err);
  };
}

// Initial connection
connect();

// Listen for messages from content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "RELAY_PAYLOAD") {
    
    const { url, method, payload: dataPayload } = message.data;

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
        socket.send(jsonStr);
        
        // Log successful relay (truncate URL for readability)
        const shortUrl = url.length > 60 ? url.substring(0, 60) + '...' : url;
        log(`>> RELAYED: [${method}] ${shortUrl}`, { sizeBytes: jsonStr.length });
        
      } catch (e) {
        console.error("[Shadow EHR] Send Failed:", e);
      }

    } else {
      const state = socket ? socket.readyState : 'NULL';
      console.warn(`[Shadow EHR] ⚠️ Dropped Packet. Socket State: ${state}. URL: ${url}`);
    }
  }
});