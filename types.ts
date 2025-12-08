export enum ScraperMode {
  PASSIVE = 'PASSIVE', // Option A: Listen only
  ACTIVE = 'ACTIVE',   // Option B: Vacuum/Crawler
}

export enum ScraperStatus {
  IDLE = 'IDLE',
  CONNECTING = 'CONNECTING',
  INTERCEPTING = 'INTERCEPTING', // Green status
  CRAWLING = 'CRAWLING',         // Amber status (high load)
  ERROR = 'ERROR'
}

export interface LogEntry {
  id: string;
  timestamp: string;
  method: string;
  endpoint: string;
  status: number;
  size: string;
  payload: any; // Raw JSON from Athena
}

export interface Patient {
  id: string;
  mrn: string;
  name: string;
  dob: string;
  gender: string;
  lastEncounter: string;
  conditions: string[];
  medications: string[];
  vitals: {
    bp: string;
    hr: number;
    temp: number;
    spo2: number;
  };
  notes: string; // Raw note text
}

// FHIR-lite structures for display
export interface AgentOutput {
  agentName: string; // e.g. "Clinical Summarizer"
  status: 'thinking' | 'complete' | 'idle';
  content: string;
  timestamp: string;
  modelUsed: string;
}

export interface LedgerEntry {
  hash: string;
  entity: string; // e.g. "Agent:RiskPredictor"
  action: string; // e.g. "Generated Risk Score"
  timestamp: string;
}
