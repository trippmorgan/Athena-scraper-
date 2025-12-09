import { LogEntry, Patient, ScraperStatus } from '../types';

type WebSocketMessage = 
  | { type: 'LOG_ENTRY'; data: LogEntry }
  | { type: 'PATIENT_UPDATE'; data: Patient }
  | { type: 'STATUS_UPDATE'; data: string };

class WebSocketService {
  private socket: WebSocket | null = null;
  private url: string = 'ws://localhost:8000/ws/frontend';
  private reconnectInterval: number = 3000;
  
  // Event callbacks
  public onLogEntry: ((log: LogEntry) => void) | null = null;
  public onPatientUpdate: ((patient: Patient) => void) | null = null;
  public onStatusChange: ((status: ScraperStatus) => void) | null = null;

  connect() {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    console.log(`[WS] Connecting to ${this.url}...`);
    this.onStatusChange?.(ScraperStatus.CONNECTING);

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log('[WS] Connected');
      this.onStatusChange?.(ScraperStatus.INTERCEPTING); // Default to INTERCEPTING when connected
    };

    this.socket.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        
        switch (message.type) {
          case 'LOG_ENTRY':
            this.onLogEntry?.(message.data);
            break;
          case 'PATIENT_UPDATE':
            this.onPatientUpdate?.(message.data);
            break;
          case 'STATUS_UPDATE':
            // Map backend status strings to frontend enums if needed
            if (message.data === 'DISCONNECTED') {
                this.onStatusChange?.(ScraperStatus.IDLE); // Chrome disconnected
            } else {
                this.onStatusChange?.(ScraperStatus.INTERCEPTING);
            }
            break;
        }
      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    this.socket.onclose = () => {
      console.log('[WS] Disconnected. Reconnecting...');
      this.onStatusChange?.(ScraperStatus.ERROR);
      this.socket = null;
      setTimeout(() => this.connect(), this.reconnectInterval);
    };

    this.socket.onerror = (err) => {
      console.error('[WS] Error:', err);
      this.socket?.close();
    };
  }

  sendMode(mode: string) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ action: "SET_MODE", mode }));
    }
  }
}

export const wsService = new WebSocketService();
