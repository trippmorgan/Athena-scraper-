/**
 * Tier 1: The Bridge
 * Injects the hook into the DOM and forwards events to the Background Service Worker.
 */

// 1. Inject the "Hook" script into the Main World
const s = document.createElement('script');
s.src = chrome.runtime.getURL('injected.js');
s.onload = function() {
    this.remove(); // Clean up the DOM tag after execution
};
(document.head || document.documentElement).appendChild(s);

// 2. Listen for the Custom Event dispatched by injected.js
window.addEventListener('SHADOW_EHR_INTERCEPT', function(e) {
    const data = e.detail;
    
    // 3. Send to Background Worker (which holds the WebSocket)
    chrome.runtime.sendMessage({
        action: "RELAY_PAYLOAD",
        data: data
    });
});