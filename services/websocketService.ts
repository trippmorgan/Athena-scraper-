import { LogEntry, Patient, ScraperStatus } from '../types';

type WebSocketMessage =
  | { type: 'LOG_ENTRY'; data: LogEntry }
  | { type: 'PATIENT_UPDATE'; data: Patient }
  | { type: 'STATUS_UPDATE'; data: string }
  | { type: 'PING'; timestamp: string }
  | { type: 'CLINICAL_UPDATE'; data: any };

// Frontend Logger with styled console output
const Logger = {
  _log: (level: string, emoji: string, msg: string, data?: any) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[Shadow EHR Frontend ${time}]`;
    const styles: Record<string, string> = {
      info: "color: #3b82f6; font-weight: bold;",
      success: "color: #10b981; font-weight: bold;",
      warn: "color: #f59e0b; font-weight: bold;",
      error: "color: #ef4444; font-weight: bold;",
      debug: "color: #8b5cf6;",
      ws: "color: #06b6d4; font-weight: bold;",
      data: "color: #22c55e; font-weight: bold;"
    };
    const style = styles[level] || styles.info;
    if (data !== undefined) {
      console.log(`%c${prefix} ${emoji} ${msg}`, style, data);
    } else {
      console.log(`%c${prefix} ${emoji} ${msg}`, style);
    }
  },
  info: (msg: string, data?: any) => Logger._log('info', 'ℹ️', msg, data),
  success: (msg: string, data?: any) => Logger._log('success', '✅', msg, data),
  warn: (msg: string, data?: any) => Logger._log('warn', '⚠️', msg, data),
  error: (msg: string, data?: any) => Logger._log('error', '❌', msg, data),
  debug: (msg: string, data?: any) => Logger._log('debug', '🔍', msg, data),
  ws: (msg: string, data?: any) => Logger._log('ws', '🔌', msg, data),
  data: (msg: string, data?: any) => Logger._log('data', '📦', msg, data),
  separator: () => console.log('%c' + '═'.repeat(50), 'color: #475569;')
};

class WebSocketService {
  private socket: WebSocket | null = null;
  private url: string = 'ws://localhost:8000/ws/frontend';
  private reconnectInterval: number = 3000;
  private reconnectAttempts: number = 0;
  private messagesReceived: number = 0;
  private patientsReceived: number = 0;
  private logsReceived: number = 0;

  // Event callbacks
  public onLogEntry: ((log: LogEntry) => void) | null = null;
  public onPatientUpdate: ((patient: Patient) => void) | null = null;
  public onStatusChange: ((status: ScraperStatus) => void) | null = null;

  connect() {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      Logger.debug('Connection already active, skipping...');
      return;
    }

    Logger.separator();
    Logger.ws(`Connecting to backend... (Attempt ${this.reconnectAttempts + 1})`);
    Logger.ws('Target URL:', this.url);
    this.onStatusChange?.(ScraperStatus.CONNECTING);

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      Logger.separator();
      Logger.success('WEBSOCKET CONNECTED TO BACKEND');
      Logger.ws('Connection details:', {
        url: this.url,
        readyState: this.socket?.readyState,
        reconnectAttempts: this.reconnectAttempts
      });
      Logger.separator();

      this.reconnectAttempts = 0;
      this.onStatusChange?.(ScraperStatus.INTERCEPTING);
    };

    this.socket.onmessage = (event) => {
      this.messagesReceived++;

      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        const msgSize = event.data.length;

        Logger.debug(`Message #${this.messagesReceived} received (${msgSize} bytes)`, { type: message.type });

        switch (message.type) {
          case 'LOG_ENTRY':
            this.logsReceived++;
            Logger.data('LOG_ENTRY received', {
              id: message.data.id,
              method: message.data.method,
              endpoint: message.data.endpoint?.substring(0, 50) + '...',
              size: message.data.size,
              totalLogs: this.logsReceived
            });
            this.onLogEntry?.(message.data);
            break;

          case 'PATIENT_UPDATE':
            this.patientsReceived++;
            Logger.separator();
            Logger.success('PATIENT UPDATE RECEIVED', {
              name: message.data.name,
              mrn: message.data.mrn,
              conditions: message.data.conditions?.length || 0,
              medications: message.data.medications?.length || 0,
              vitals: message.data.vitals,
              totalPatientUpdates: this.patientsReceived
            });
            Logger.separator();
            this.onPatientUpdate?.(message.data);
            break;

          case 'STATUS_UPDATE':
            Logger.info('STATUS_UPDATE received:', message.data);
            if (message.data === 'DISCONNECTED') {
              Logger.warn('Chrome extension disconnected from backend');
              this.onStatusChange?.(ScraperStatus.IDLE);
            } else if (message.data === 'CONNECTED') {
              Logger.success('Chrome extension connected to backend');
              this.onStatusChange?.(ScraperStatus.INTERCEPTING);
            } else {
              this.onStatusChange?.(ScraperStatus.INTERCEPTING);
            }
            break;

          case 'PING':
            // Respond to heartbeat with PONG to keep connection alive
            Logger.debug('Heartbeat PING received, sending PONG');
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
              this.socket.send(JSON.stringify({ action: 'PONG', timestamp: new Date().toISOString() }));
            }
            break;

          case 'CLINICAL_UPDATE':
            // Clinical data from interpreters - forward to patient update handler
            Logger.debug('Clinical update received:', message.data);
            break;

          default:
            Logger.warn('Unknown message type:', message);
        }
      } catch (err) {
        Logger.error('Failed to parse message:', err);
        Logger.debug('Raw message data:', event.data?.substring(0, 200));
      }
    };

    this.socket.onclose = (event) => {
      Logger.separator();
      Logger.warn('WEBSOCKET DISCONNECTED');
      Logger.ws('Close details:', {
        code: event.code,
        reason: event.reason || 'No reason',
        wasClean: event.wasClean
      });

      this.onStatusChange?.(ScraperStatus.ERROR);
      this.socket = null;
      this.reconnectAttempts++;

      const delay = Math.min(this.reconnectInterval * this.reconnectAttempts, 30000);
      Logger.info(`Reconnecting in ${delay/1000} seconds...`);
      setTimeout(() => this.connect(), delay);
    };

    this.socket.onerror = (err) => {
      Logger.error('WebSocket error occurred', {
        readyState: this.socket?.readyState,
        url: this.url
      });
      this.socket?.close();
    };
  }

  sendMode(mode: string) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const message = { action: "SET_MODE", mode };
      Logger.info('Sending mode change:', message);
      this.socket.send(JSON.stringify(message));
    } else {
      Logger.warn('Cannot send mode - socket not connected');
    }
  }

  getStats() {
    const stats = {
      connected: this.socket?.readyState === WebSocket.OPEN,
      messagesReceived: this.messagesReceived,
      logsReceived: this.logsReceived,
      patientsReceived: this.patientsReceived,
      reconnectAttempts: this.reconnectAttempts
    };
    Logger.info('Current stats:', stats);
    return stats;
  }

  disconnect() {
    Logger.info('Manual disconnect requested');
    this.socket?.close();
    this.socket = null;
  }
}

export const wsService = new WebSocketService();

// Log service initialization
Logger.info('WebSocket service initialized');
Logger.info('Target backend:', 'ws://localhost:8000/ws/frontend');
