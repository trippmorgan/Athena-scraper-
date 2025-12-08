import React, { useState, useEffect, useCallback } from 'react';
import { 
  LogEntry, 
  ScraperMode, 
  ScraperStatus, 
  Patient, 
  AgentOutput,
  LedgerEntry 
} from './types';
import { generateLogEntry, fetchMockPatient } from './services/mockScraperService';
import { generateAgentResponse } from './services/geminiService';
import { LiveLog } from './components/LiveLog';
import { AgentCard } from './components/AgentCard';
import { MirrorLedger } from './components/MirrorLedger';
import { ScraperControl } from './components/ScraperControl';
import { 
  Stethoscope, 
  BrainCircuit, 
  FileText, 
  AlertOctagon, 
  Activity, 
  User, 
  LayoutDashboard
} from 'lucide-react';

const App: React.FC = () => {
  // --- State ---
  const [scraperMode, setScraperMode] = useState<ScraperMode>(ScraperMode.PASSIVE);
  const [status, setStatus] = useState<ScraperStatus>(ScraperStatus.INTERCEPTING);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentPatient, setCurrentPatient] = useState<Patient | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);

  // Agents State
  const [summaryAgent, setSummaryAgent] = useState<AgentOutput>({ agentName: 'Clinical Summarizer', status: 'idle', content: '', timestamp: '', modelUsed: '' });
  const [riskAgent, setRiskAgent] = useState<AgentOutput>({ agentName: 'Risk Predictor', status: 'idle', content: '', timestamp: '', modelUsed: '' });
  const [codingAgent, setCodingAgent] = useState<AgentOutput>({ agentName: 'Coding Assistant', status: 'idle', content: '', timestamp: '', modelUsed: '' });

  // --- Effects ---

  // 1. Simulate Incoming Scraper Logs (Live Feed)
  useEffect(() => {
    // Speed depends on mode: Active = fast, Passive = slower
    const intervalTime = scraperMode === ScraperMode.ACTIVE ? 800 : 3500;
    
    const interval = setInterval(() => {
      const newLog = generateLogEntry(scraperMode);
      setLogs(prev => [...prev.slice(-49), newLog]); // Keep last 50
    }, intervalTime);

    // Update Status based on mode
    setStatus(scraperMode === ScraperMode.ACTIVE ? ScraperStatus.CRAWLING : ScraperStatus.INTERCEPTING);

    return () => clearInterval(interval);
  }, [scraperMode]);

  // 2. Simulate detecting a new "Full Patient Chart" load
  // In a real app, this triggers when we detect '/chart/patient/{id}/summary'
  useEffect(() => {
    const triggerPatientLoad = async () => {
      // Clear agents
      setSummaryAgent(prev => ({ ...prev, status: 'thinking', content: '' }));
      setRiskAgent(prev => ({ ...prev, status: 'thinking', content: '' }));
      setCodingAgent(prev => ({ ...prev, status: 'thinking', content: '' }));

      // Fetch Mock Patient (Simulating JSON intercept)
      const patient = await fetchMockPatient();
      setCurrentPatient(patient);

      // Add to Ledger
      addToLedger('ScraperEngine', `Intercepted Chart: ${patient.mrn}`);

      // Trigger Agents
      runAgents(patient);
    };

    // Trigger periodically to demo the "Live" nature
    const demoTimer = setInterval(triggerPatientLoad, 15000); 
    
    // Initial load
    triggerPatientLoad();

    return () => clearInterval(demoTimer);
  }, [scraperMode]);

  // --- Helpers ---

  const addToLedger = (entity: string, action: string) => {
    const hash = Math.random().toString(16).substring(2);
    setLedger(prev => [{ hash, entity, action, timestamp: new Date().toISOString() }, ...prev]);
  };

  const runAgents = async (patient: Patient) => {
    // 1. Summarizer Agent
    generateAgentResponse(
      'Clinical Summarizer',
      'You are an expert Medical Scribe. Create a concise SOAP note summary based on the provided patient JSON. Use professional medical abbreviations.',
      patient
    ).then(res => {
      setSummaryAgent(res);
      addToLedger('Agent:Summarizer', 'Generated SOAP Note');
    });

    // 2. Risk Agent
    generateAgentResponse(
      'Risk Predictor',
      'You are a Clinical Risk AI. Analyze vitals, conditions, and meds. Output a Risk Score (0-100) and a brief 1-sentence rationale for the score. Format: "Risk Score: X/100. Rationale: ..."',
      patient
    ).then(res => {
      setRiskAgent(res);
      addToLedger('Agent:Risk', 'Calculated Risk Score');
    });

    // 3. Coding Agent
    generateAgentResponse(
      'Coding Assistant',
      'You are a Medical Coder. Suggest ICD-10 codes for the conditions and CPT codes for a standard office visit level 4 based on this data. Format as a bulleted list.',
      patient
    ).then(res => {
      setCodingAgent(res);
      addToLedger('Agent:Coder', 'Generated Billing Codes');
    });
  };

  // --- Render ---

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-950 text-slate-200 overflow-hidden">
      {/* Header */}
      <header className="h-16 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between px-6 shrink-0 z-10 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="bg-cyan-500/10 p-2 rounded-lg border border-cyan-500/20">
            <LayoutDashboard size={20} className="text-cyan-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white leading-tight">Shadow EHR <span className="text-slate-500 font-normal">| Command Center</span></h1>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              PlaudAI Database Connected
            </div>
          </div>
        </div>

        {/* Central Status */}
        <div className="hidden md:flex items-center gap-8">
           <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">Active Patient</p>
              <p className="font-mono text-cyan-400 font-bold">{currentPatient ? currentPatient.name : 'Loading...'}</p>
           </div>
           <div className="h-8 w-px bg-slate-800"></div>
           <div className="text-left">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">MRN</p>
              <p className="font-mono text-slate-300">{currentPatient ? currentPatient.mrn : '---'}</p>
           </div>
        </div>

        {/* Controls */}
        <div className="w-64">
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
                {currentPatient ? JSON.stringify(currentPatient, null, 2) : '// Waiting for intercept...'}
              </pre>
           </div>
        </div>

        {/* Center Column: Intelligence (Agents) */}
        <div className="col-span-6 bg-slate-925 flex flex-col p-6 overflow-y-auto">
          <div className="mb-6 flex items-end justify-between">
            <h2 className="text-xl font-light text-white">Clinical Intelligence Swarm</h2>
            <span className="text-xs text-slate-500">Processing Node: Gemini 2.5 Flash</span>
          </div>

          <div className="grid grid-cols-1 gap-4 mb-4">
             {/* Primary Agent: Summarizer */}
             <div className="h-64">
               <AgentCard 
                 output={summaryAgent} 
                 icon={<FileText size={18} />}
                 colorClass="border-cyan-800/50 bg-slate-900/80 shadow-cyan-900/20" 
               />
             </div>
          </div>

          <div className="grid grid-cols-2 gap-4 flex-1">
             {/* Secondary Agents */}
             <div className="h-64">
               <AgentCard 
                 output={riskAgent} 
                 icon={<AlertOctagon size={18} />}
                 colorClass="border-red-900/30 bg-slate-900/50"
               />
             </div>
             <div className="h-64">
               <AgentCard 
                 output={codingAgent} 
                 icon={<BrainCircuit size={18} />}
                 colorClass="border-purple-900/30 bg-slate-900/50"
               />
             </div>
          </div>
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