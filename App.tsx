import React, { useState, useEffect, useRef } from 'react';
import {
  LogEntry,
  ScraperMode,
  ScraperStatus,
  Patient,
  LedgerEntry
} from './types';
import { wsService } from './services/websocketService'; // Real WS Service
import { LiveLog } from './components/LiveLog';
import { MirrorLedger } from './components/MirrorLedger';
import { ScraperControl } from './components/ScraperControl';
import { SurgicalDashboard } from './components/SurgicalDashboard';
import {
  Activity,
  LayoutDashboard,
  User,
  Search,
  History
} from 'lucide-react';

const App: React.FC = () => {
  // --- State ---
  const [scraperMode, setScraperMode] = useState<ScraperMode>(ScraperMode.PASSIVE);
  const [status, setStatus] = useState<ScraperStatus>(ScraperStatus.CONNECTING);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentPatient, setCurrentPatient] = useState<Patient | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  
  // History & Search State
  const [patientHistory, setPatientHistory] = useState<Patient[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearchResults, setShowSearchResults] = useState(false);

  // Use refs to prevent stale closures in WS callbacks
  const patientRef = useRef<Patient | null>(null);

  // --- Effects ---

  // 1. Initialize WebSocket Connection
  useEffect(() => {
    // Setup Callbacks
    wsService.onLogEntry = (log) => {
        setLogs(prev => [...prev.slice(-49), log]);
    };

    wsService.onStatusChange = (newStatus) => {
        setStatus(newStatus);
    };

    wsService.onPatientUpdate = (patient) => {
        // Only update if it's a new patient or significant change
        if (patient.mrn !== patientRef.current?.mrn) {
            console.log("New Patient Detected:", patient.name);
            patientRef.current = patient;
            setCurrentPatient(patient);
            
            // Add to history if unique
            setPatientHistory(prev => {
                if (prev.some(p => p.mrn === patient.mrn)) return prev;
                return [patient, ...prev];
            });
            
            // Log to Ledger
            addToLedger('ScraperEngine', `Intercepted Chart: ${patient.mrn}`);
        }
    };

    // Connect
    wsService.connect();

    return () => {
        // Optional: Disconnect logic if needed
    };
  }, []);

  // 2. Handle Mode Switching
  useEffect(() => {
    wsService.sendMode(scraperMode);
  }, [scraperMode]);

  // --- Helpers ---

  const addToLedger = (entity: string, action: string) => {
    const hash = Math.random().toString(16).substring(2);
    setLedger(prev => [{ hash, entity, action, timestamp: new Date().toISOString() }, ...prev]);
  };

  const handlePatientSelect = (patient: Patient) => {
      setCurrentPatient(patient);
      patientRef.current = patient;
      setSearchQuery('');
      setShowSearchResults(false);
  };

  const filteredPatients = patientHistory.filter(p =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.mrn.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // --- Render ---

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-950 text-slate-200 overflow-hidden">
      {/* Header */}
      <header className="h-16 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between px-6 shrink-0 z-10 backdrop-blur-sm">
        <div className="flex items-center gap-3 w-64">
          <div className="bg-cyan-500/10 p-2 rounded-lg border border-cyan-500/20">
            <LayoutDashboard size={20} className="text-cyan-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white leading-tight">Shadow EHR <span className="text-slate-500 font-normal">| Command Center</span></h1>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className={`w-2 h-2 rounded-full ${status === ScraperStatus.ERROR ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
              {status === ScraperStatus.CONNECTING ? 'Connecting to Engine...' : 'PlaudAI Database Connected'}
            </div>
          </div>
        </div>

        {/* Central Search Bar */}
        <div className="flex-1 max-w-xl mx-4 relative z-50">
           <div className="relative group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-cyan-400 transition-colors" size={16} />
              <input 
                type="text" 
                placeholder="Search History (MRN or Name)..." 
                className="w-full bg-slate-950/50 border border-slate-700 rounded-full py-2 pl-10 pr-4 text-sm text-slate-200 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 transition-all placeholder:text-slate-600"
                onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setShowSearchResults(true);
                }}
                onFocus={() => setShowSearchResults(true)}
                // Delay blur to allow click on result
                onBlur={() => setTimeout(() => setShowSearchResults(false), 200)}
                value={searchQuery}
              />
           </div>

           {/* Search Results Dropdown */}
           {showSearchResults && (searchQuery || patientHistory.length > 0) && (
             <div className="absolute top-full left-0 right-0 mt-2 bg-slate-900 border border-slate-700 rounded-lg shadow-xl shadow-black/50 overflow-hidden max-h-80 overflow-y-auto">
                <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-slate-500 bg-slate-950/50 border-b border-slate-800 font-bold flex items-center gap-2">
                    <History size={10} /> Recent Patients
                </div>
                {filteredPatients.length === 0 ? (
                    <div className="p-4 text-center text-slate-600 text-sm italic">
                        {searchQuery ? 'No matching patients found.' : 'No history yet.'}
                    </div>
                ) : (
                    filteredPatients.map(p => (
                        <div 
                            key={p.mrn}
                            className="px-4 py-3 hover:bg-slate-800 cursor-pointer border-b border-slate-800/50 last:border-0 transition-colors flex justify-between items-center group"
                            onClick={() => handlePatientSelect(p)}
                        >
                            <div>
                                <div className="text-sm font-bold text-slate-200 group-hover:text-cyan-400 transition-colors">{p.name}</div>
                                <div className="text-xs text-slate-500 font-mono">{p.mrn}</div>
                            </div>
                            <div className="text-[10px] text-slate-600 group-hover:text-slate-400">
                                {p.lastEncounter}
                            </div>
                        </div>
                    ))
                )}
             </div>
           )}
        </div>

        {/* Right Controls */}
        <div className="w-64 flex justify-end">
          <ScraperControl 
            mode={scraperMode} 
            status={status} 
            onModeChange={setScraperMode} 
          />
        </div>
      </header>

      {/* Main Grid */}
      <main className="flex-1 grid grid-cols-12 gap-0 overflow-hidden">
        
        {/* Left Column: Data Ingestion (Logs) */}
        <div className="col-span-3 border-r border-slate-800 bg-slate-950/50 flex flex-col p-4 gap-4">
           <h2 className="text-xs font-bold uppercase tracking-widest text-slate-500 flex items-center gap-2">
            <Activity size={14} /> AthenaNet Traffic
           </h2>
           <div className="flex-1 overflow-hidden rounded-lg">
             <LiveLog logs={logs} status={status} />
           </div>
           
           {/* Raw Patient Data Viewer (Mini) */}
           <div className="h-1/3 bg-slate-900 rounded-lg border border-slate-800 p-3 overflow-hidden flex flex-col">
              <h3 className="text-xs text-slate-400 mb-2 font-mono flex items-center gap-2">
                <User size={12} /> Raw JSON Object
              </h3>
              <pre className="text-[10px] text-slate-500 font-mono overflow-auto flex-1 custom-scrollbar">
                {currentPatient ? JSON.stringify(currentPatient, null, 2) : '// Navigate to a chart in Athena...'}
              </pre>
           </div>
        </div>

        {/* Center Column: Surgical Dashboard */}
        <div className="col-span-6 bg-slate-925 overflow-hidden">
          <SurgicalDashboard
            onSearch={(mrn) => {
              // Trigger extension fetch
              console.log('Fetching MRN:', mrn);
            }}
          />
        </div>

        {/* Right Column: Audit (Mirror Ledger) */}
        <div className="col-span-3 border-l border-slate-800 bg-slate-950/80 p-4">
           <MirrorLedger entries={ledger} />
        </div>

      </main>
    </div>
  );
};

export default App;