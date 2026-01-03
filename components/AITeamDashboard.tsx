import React, { useState, useEffect, useCallback } from 'react';

/**
 * EHR Bridge AI Team Dashboard
 *
 * Visual representation of the multi-agent architecture:
 * - Claude (CEO): Session detection, orchestration
 * - Gemini (CTO): Data processing
 * - Codex (Principal Engineer): Code generation
 */

interface AgentState {
  status: 'idle' | 'active' | 'processing' | 'error';
  lastAction: string | null;
  taskCount: number;
}

interface SessionInfo {
  isLoggedIn: boolean;
  sessionHealth: 'good' | 'warning' | 'expired' | 'error';
  concerns?: string[];
  recommendations?: string[];
}

interface LogEntry {
  time: string;
  agent: 'claude' | 'gemini' | 'codex';
  action: string;
}

interface DashboardState {
  session: SessionInfo | null;
  recording: boolean;
  debuggerAttached: boolean;
  agents: {
    claude: AgentState;
    gemini: AgentState;
    codex: AgentState;
  };
  capturedRequests: number;
  discoveredEndpoints: Array<{
    pattern: string;
    dataType: string;
    useCount: number;
  }>;
  logs: LogEntry[];
  stats: {
    totalCaptured: number;
    apiCallsAnalyzed: number;
    delegatedToGemini: number;
    delegatedToCodex: number;
    endpointsDiscovered: number;
  };
}

interface ApiKeys {
  claude: string;
  gemini: string;
  openai: string;
}

const AITeamDashboard: React.FC = () => {
  const [state, setState] = useState<DashboardState>({
    session: null,
    recording: false,
    debuggerAttached: false,
    agents: {
      claude: { status: 'idle', lastAction: null, taskCount: 0 },
      gemini: { status: 'idle', lastAction: null, taskCount: 0 },
      codex: { status: 'idle', lastAction: null, taskCount: 0 }
    },
    capturedRequests: 0,
    discoveredEndpoints: [],
    logs: [],
    stats: {
      totalCaptured: 0,
      apiCallsAnalyzed: 0,
      delegatedToGemini: 0,
      delegatedToCodex: 0,
      endpointsDiscovered: 0
    }
  });

  const [apiKeys, setApiKeys] = useState<ApiKeys>({
    claude: '',
    gemini: '',
    openai: ''
  });

  const [showConfig, setShowConfig] = useState(false);
  const [mrn, setMrn] = useState('');
  const [extracting, setExtracting] = useState(false);

  // Add log entry helper
  const addLog = useCallback((agent: 'claude' | 'gemini' | 'codex', action: string) => {
    setState(prev => ({
      ...prev,
      logs: [...prev.logs, {
        time: new Date().toLocaleTimeString(),
        agent,
        action
      }].slice(-30) // Keep last 30 logs
    }));
  }, []);

  // Listen for messages from background script
  useEffect(() => {
    const handleMessage = (message: { type: string; data?: unknown; task?: string }) => {
      switch (message.type) {
        case 'SESSION_UPDATE':
          setState(prev => ({
            ...prev,
            session: message.data as SessionInfo,
            agents: {
              ...prev.agents,
              claude: {
                ...prev.agents.claude,
                status: 'active',
                lastAction: 'Session analysis',
                taskCount: prev.agents.claude.taskCount + 1
              }
            }
          }));
          addLog('claude', 'Analyzed session state');
          setTimeout(() => {
            setState(prev => ({
              ...prev,
              agents: { ...prev.agents, claude: { ...prev.agents.claude, status: 'idle' } }
            }));
          }, 2000);
          break;

        case 'DEBUGGER_STATUS':
          setState(prev => ({
            ...prev,
            debuggerAttached: (message.data as { attached: boolean }).attached
          }));
          break;

        case 'REQUEST_CAPTURED':
          const reqData = message.data as { url: string; stats: DashboardState['stats'] };
          setState(prev => ({
            ...prev,
            capturedRequests: reqData.stats?.totalCaptured || prev.capturedRequests + 1,
            stats: reqData.stats || prev.stats,
            agents: {
              ...prev.agents,
              claude: { ...prev.agents.claude, status: 'processing' }
            }
          }));
          addLog('claude', `Captured: ${reqData.url?.split('/').pop() || 'request'}`);
          setTimeout(() => {
            setState(prev => ({
              ...prev,
              agents: { ...prev.agents, claude: { ...prev.agents.claude, status: 'idle' } }
            }));
          }, 1000);
          break;

        case 'ENDPOINT_DISCOVERED':
          const endpoint = message.data as { pattern: string; dataType: string };
          setState(prev => ({
            ...prev,
            discoveredEndpoints: [...prev.discoveredEndpoints, { ...endpoint, useCount: 1 }]
          }));
          addLog('codex', `Discovered endpoint: ${endpoint.pattern}`);
          break;

        case 'GEMINI_RESULT':
          setState(prev => ({
            ...prev,
            agents: {
              ...prev.agents,
              gemini: {
                status: 'active',
                lastAction: message.task || 'Data processing',
                taskCount: prev.agents.gemini.taskCount + 1
              }
            }
          }));
          addLog('gemini', `Processed: ${message.task}`);
          setTimeout(() => {
            setState(prev => ({
              ...prev,
              agents: { ...prev.agents, gemini: { ...prev.agents.gemini, status: 'idle' } }
            }));
          }, 2000);
          break;

        case 'CODEX_RESULT':
          setState(prev => ({
            ...prev,
            agents: {
              ...prev.agents,
              codex: {
                status: 'active',
                lastAction: message.task || 'Code generation',
                taskCount: prev.agents.codex.taskCount + 1
              }
            }
          }));
          addLog('codex', `Generated: ${message.task}`);
          setTimeout(() => {
            setState(prev => ({
              ...prev,
              agents: { ...prev.agents, codex: { ...prev.agents.codex, status: 'idle' } }
            }));
          }, 2000);
          break;
      }
    };

    // Check if running in extension context
    if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
      chrome.runtime.onMessage.addListener(handleMessage);
      return () => chrome.runtime.onMessage.removeListener(handleMessage);
    }
  }, [addLog]);

  // Load initial state and API keys
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      // Get CEO state
      chrome.runtime.sendMessage({ type: 'CEO_GET_STATE' }, (response) => {
        if (response) {
          setState(prev => ({
            ...prev,
            recording: response.isRecording || false,
            debuggerAttached: response.debuggerAttached || false,
            session: response.sessionInfo,
            stats: response.stats || prev.stats
          }));
        }
      });

      // Get discovered endpoints
      chrome.runtime.sendMessage({ type: 'CEO_GET_ENDPOINTS' }, (endpoints) => {
        if (endpoints && Array.isArray(endpoints)) {
          setState(prev => ({ ...prev, discoveredEndpoints: endpoints }));
        }
      });
    }

    // Load API keys from storage
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['anthropicApiKey', 'geminiApiKey', 'openaiApiKey'], (result) => {
        setApiKeys({
          claude: result.anthropicApiKey ? '••••••••' : '',
          gemini: result.geminiApiKey ? '••••••••' : '',
          openai: result.openaiApiKey ? '••••••••' : ''
        });
      });
    }
  }, []);

  const saveApiKeys = () => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      const keysToSave: Record<string, string> = {};

      if (apiKeys.claude && !apiKeys.claude.includes('••')) {
        keysToSave.anthropicApiKey = apiKeys.claude;
      }
      if (apiKeys.gemini && !apiKeys.gemini.includes('••')) {
        keysToSave.geminiApiKey = apiKeys.gemini;
      }
      if (apiKeys.openai && !apiKeys.openai.includes('••')) {
        keysToSave.openaiApiKey = apiKeys.openai;
      }

      if (Object.keys(keysToSave).length > 0) {
        chrome.storage.local.set(keysToSave);
        addLog('claude', 'API keys updated');
      }
    }
    setShowConfig(false);
  };

  const toggleRecording = async () => {
    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      const messageType = state.recording ? 'CEO_STOP_RECORDING' : 'CEO_START_RECORDING';

      chrome.runtime.sendMessage({ type: messageType }, (response) => {
        setState(prev => ({
          ...prev,
          recording: response?.recording ?? !prev.recording,
          debuggerAttached: response?.debuggerAttached ?? prev.debuggerAttached
        }));
        addLog('claude', state.recording ? 'Stopped recording' : 'Started recording');
      });
    }
  };

  const detectSession = async () => {
    if (typeof chrome !== 'undefined' && chrome.tabs?.query && chrome.runtime?.sendMessage) {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (tab?.id) {
        setState(prev => ({
          ...prev,
          agents: { ...prev.agents, claude: { ...prev.agents.claude, status: 'processing' } }
        }));

        chrome.runtime.sendMessage({ type: 'CEO_DETECT_SESSION', tabId: tab.id }, (result) => {
          setState(prev => ({
            ...prev,
            session: result,
            agents: { ...prev.agents, claude: { ...prev.agents.claude, status: 'idle' } }
          }));
        });
      }
    }
  };

  const executeExtraction = async () => {
    if (!mrn.trim()) return;

    setExtracting(true);
    addLog('claude', `Planning extraction strategy for MRN: ${mrn}`);

    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'CEO_EXECUTE_STRATEGY', mrn: mrn.trim() }, (result) => {
        setExtracting(false);
        if (result?.success) {
          addLog('claude', 'Extraction complete');
        } else {
          addLog('claude', `Extraction failed: ${result?.error || 'Unknown error'}`);
        }
      });
    } else {
      setExtracting(false);
    }
  };

  const exportData = () => {
    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'CEO_EXPORT_DATA' }, (data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ehr-bridge-export-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        addLog('claude', 'Data exported');
      });
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-blue-400">EHR Bridge AI Team</h1>
          <p className="text-slate-400">Multi-Agent Athena Integration System</p>
        </div>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="px-4 py-2 bg-slate-700 rounded-lg hover:bg-slate-600 transition-colors"
        >
          <span className="mr-2">⚙️</span>Configure API Keys
        </button>
      </div>

      {/* API Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-slate-800 p-6 rounded-lg w-96 border border-slate-700">
            <h2 className="text-xl font-bold mb-4">API Configuration</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  <span className="inline-block w-4 h-4 bg-violet-500 rounded mr-2"></span>
                  Claude API Key (CEO)
                </label>
                <input
                  type="password"
                  value={apiKeys.claude}
                  onChange={(e) => setApiKeys(prev => ({ ...prev, claude: e.target.value }))}
                  className="w-full bg-slate-700 rounded px-3 py-2 focus:ring-2 focus:ring-violet-500 outline-none"
                  placeholder="sk-ant-..."
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  <span className="inline-block w-4 h-4 bg-emerald-500 rounded mr-2"></span>
                  Gemini API Key (CTO)
                </label>
                <input
                  type="password"
                  value={apiKeys.gemini}
                  onChange={(e) => setApiKeys(prev => ({ ...prev, gemini: e.target.value }))}
                  className="w-full bg-slate-700 rounded px-3 py-2 focus:ring-2 focus:ring-emerald-500 outline-none"
                  placeholder="AIza..."
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">
                  <span className="inline-block w-4 h-4 bg-orange-500 rounded mr-2"></span>
                  OpenAI API Key (Principal Engineer)
                </label>
                <input
                  type="password"
                  value={apiKeys.openai}
                  onChange={(e) => setApiKeys(prev => ({ ...prev, openai: e.target.value }))}
                  className="w-full bg-slate-700 rounded px-3 py-2 focus:ring-2 focus:ring-orange-500 outline-none"
                  placeholder="sk-..."
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowConfig(false)}
                className="px-4 py-2 bg-slate-600 rounded hover:bg-slate-500"
              >
                Cancel
              </button>
              <button
                onClick={saveApiKeys}
                className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-500"
              >
                Save Keys
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AI Team Org Chart */}
      <div className="mb-8">
        <div className="flex flex-col items-center">
          {/* CEO - Claude */}
          <AgentCard
            name="Claude"
            role="CEO"
            title="Chief Intelligence Officer"
            status={state.agents.claude.status}
            lastAction={state.agents.claude.lastAction}
            taskCount={state.agents.claude.taskCount}
            color="violet"
            icon="👔"
            responsibilities={[
              'Session Detection',
              'Traffic Orchestration',
              'Strategic Decisions',
              'HIPAA Oversight'
            ]}
          />

          {/* Connector Line */}
          <div className="w-px h-8 bg-slate-600"></div>
          <div className="w-64 h-px bg-slate-600"></div>

          {/* CTO & Principal Engineer */}
          <div className="flex gap-8 mt-2">
            <div className="flex flex-col items-center">
              <div className="w-px h-8 bg-slate-600"></div>
              <AgentCard
                name="Gemini"
                role="CTO"
                title="Chief Data Scientist"
                status={state.agents.gemini.status}
                lastAction={state.agents.gemini.lastAction}
                taskCount={state.agents.gemini.taskCount}
                color="emerald"
                icon="🔬"
                responsibilities={[
                  'Clinical Data Processing',
                  'FHIR Transformation',
                  'Medical Context',
                  'Surgical Summaries'
                ]}
              />
            </div>

            <div className="flex flex-col items-center">
              <div className="w-px h-8 bg-slate-600"></div>
              <AgentCard
                name="Codex"
                role="Principal Engineer"
                title="DevOps Architect"
                status={state.agents.codex.status}
                lastAction={state.agents.codex.lastAction}
                taskCount={state.agents.codex.taskCount}
                color="orange"
                icon="🛠️"
                responsibilities={[
                  'Endpoint Discovery',
                  'Fetch Logic Generation',
                  'Parser Creation',
                  'Code Scaffolding'
                ]}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Control Panel */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
          <h3 className="text-sm text-slate-400 mb-2">Session Status</h3>
          <div className={`text-lg font-bold ${state.session?.isLoggedIn ? 'text-emerald-400' : 'text-red-400'}`}>
            {state.session?.isLoggedIn ? '✓ Logged In' : '✗ Not Detected'}
          </div>
          {state.session?.sessionHealth && (
            <div className={`text-sm ${
              state.session.sessionHealth === 'good' ? 'text-emerald-400' :
              state.session.sessionHealth === 'warning' ? 'text-amber-400' : 'text-red-400'
            }`}>
              Health: {state.session.sessionHealth}
            </div>
          )}
          <button
            onClick={detectSession}
            className="mt-2 px-3 py-1 bg-blue-600 rounded text-sm hover:bg-blue-500 transition-colors"
          >
            Detect Session
          </button>
        </div>

        <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
          <h3 className="text-sm text-slate-400 mb-2">Traffic Recording</h3>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${state.recording ? 'bg-red-500 animate-pulse' : 'bg-slate-500'}`}></div>
            <span className={`text-lg font-bold ${state.recording ? 'text-emerald-400' : 'text-slate-400'}`}>
              {state.recording ? 'Recording' : 'Stopped'}
            </span>
          </div>
          {state.debuggerAttached && (
            <div className="text-xs text-emerald-400 mt-1">Debugger attached</div>
          )}
          <button
            onClick={toggleRecording}
            className={`mt-2 px-3 py-1 rounded text-sm transition-colors ${
              state.recording
                ? 'bg-red-600 hover:bg-red-500'
                : 'bg-emerald-600 hover:bg-emerald-500'
            }`}
          >
            {state.recording ? 'Stop' : 'Start'} Recording
          </button>
        </div>

        <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
          <h3 className="text-sm text-slate-400 mb-2">Captured Data</h3>
          <div className="text-2xl font-bold text-blue-400">
            {state.stats.totalCaptured}
          </div>
          <div className="text-sm text-slate-400">
            API calls captured
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {state.stats.apiCallsAnalyzed} analyzed
          </div>
        </div>

        <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
          <h3 className="text-sm text-slate-400 mb-2">Endpoints Discovered</h3>
          <div className="text-2xl font-bold text-violet-400">
            {state.discoveredEndpoints.length}
          </div>
          <div className="text-sm text-slate-400">
            Reusable patterns
          </div>
          <div className="text-xs text-slate-500 mt-1">
            → Gemini: {state.stats.delegatedToGemini} | Codex: {state.stats.delegatedToCodex}
          </div>
        </div>
      </div>

      {/* Active Fetch Panel */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 mb-8">
        <h3 className="text-lg font-bold mb-4">Execute Extraction Strategy</h3>
        <div className="flex gap-4">
          <input
            type="text"
            value={mrn}
            onChange={(e) => setMrn(e.target.value)}
            placeholder="Enter Patient MRN..."
            className="flex-1 bg-slate-700 rounded px-4 py-2 focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <button
            onClick={executeExtraction}
            disabled={extracting || !mrn.trim()}
            className={`px-6 py-2 rounded font-bold transition-colors ${
              extracting ? 'bg-slate-600 cursor-wait' :
              !mrn.trim() ? 'bg-slate-600 cursor-not-allowed' :
              'bg-blue-600 hover:bg-blue-500'
            }`}
          >
            {extracting ? 'Extracting...' : 'Execute Strategy'}
          </button>
          <button
            onClick={exportData}
            className="px-4 py-2 bg-violet-600 rounded hover:bg-violet-500 transition-colors"
          >
            Export Data
          </button>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          Claude CEO will plan the optimal extraction strategy using discovered endpoints
        </p>
      </div>

      {/* Activity Log */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-lg font-bold mb-4">Agent Activity Log</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto font-mono text-sm">
          {state.logs.length === 0 ? (
            <p className="text-slate-500 text-center py-4">
              No activity yet. Start recording to see agent actions.
            </p>
          ) : (
            state.logs.slice().reverse().map((log, i) => (
              <div key={i} className="flex items-center gap-3 py-1 border-b border-slate-700/50">
                <span className="text-slate-500 w-20 text-xs">{log.time}</span>
                <AgentBadge agent={log.agent} />
                <span className="text-slate-300 truncate">{log.action}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Discovered Endpoints */}
      {state.discoveredEndpoints.length > 0 && (
        <div className="mt-8 bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-lg font-bold mb-4">Discovered Endpoints</h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {state.discoveredEndpoints.map((endpoint, i) => (
              <div key={i} className="flex items-center gap-3 text-sm font-mono bg-slate-700/50 rounded px-3 py-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  endpoint.dataType === 'medication' ? 'bg-blue-600' :
                  endpoint.dataType === 'lab' ? 'bg-emerald-600' :
                  endpoint.dataType === 'problem' ? 'bg-amber-600' :
                  'bg-slate-600'
                }`}>
                  {endpoint.dataType}
                </span>
                <span className="text-slate-300 truncate flex-1">{endpoint.pattern}</span>
                <span className="text-slate-500 text-xs">{endpoint.useCount}x</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Agent Card Component
interface AgentCardProps {
  name: string;
  role: string;
  title: string;
  status: AgentState['status'];
  lastAction: string | null;
  taskCount: number;
  color: 'violet' | 'emerald' | 'orange';
  icon: string;
  responsibilities: string[];
}

const AgentCard: React.FC<AgentCardProps> = ({
  name, role, title, status, lastAction, taskCount, color, icon, responsibilities
}) => {
  const colorClasses = {
    violet: {
      bg: 'bg-violet-900/50',
      border: 'border-violet-500',
      text: 'text-violet-400',
      badge: 'bg-violet-600'
    },
    emerald: {
      bg: 'bg-emerald-900/50',
      border: 'border-emerald-500',
      text: 'text-emerald-400',
      badge: 'bg-emerald-600'
    },
    orange: {
      bg: 'bg-orange-900/50',
      border: 'border-orange-500',
      text: 'text-orange-400',
      badge: 'bg-orange-600'
    }
  };

  const c = colorClasses[color];

  return (
    <div className={`${c.bg} border ${c.border} rounded-lg p-4 w-64 transition-all hover:scale-105`}>
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <div className={`font-bold ${c.text}`}>{name}</div>
          <div className="text-xs text-slate-400">{role} - {title}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <div className={`w-2 h-2 rounded-full transition-colors ${
          status === 'active' || status === 'processing' ? 'bg-emerald-400 animate-pulse' :
          status === 'error' ? 'bg-red-400' : 'bg-slate-500'
        }`}></div>
        <span className="text-sm text-slate-300">
          {status === 'active' ? 'Active' :
           status === 'processing' ? 'Processing...' :
           status === 'error' ? 'Error' : 'Idle'}
        </span>
        <span className="text-xs text-slate-500 ml-auto">{taskCount} tasks</span>
      </div>

      {lastAction && (
        <div className="text-xs text-slate-400 mb-3 truncate" title={lastAction}>
          Last: {lastAction}
        </div>
      )}

      <div className="border-t border-slate-700 pt-2">
        <div className="text-xs text-slate-500 mb-1">Responsibilities:</div>
        <div className="flex flex-wrap gap-1">
          {responsibilities.map((r, i) => (
            <span key={i} className="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-400">
              {r}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

// Agent Badge Component
interface AgentBadgeProps {
  agent: 'claude' | 'gemini' | 'codex';
}

const AgentBadge: React.FC<AgentBadgeProps> = ({ agent }) => {
  const configs = {
    claude: { color: 'bg-violet-600', label: 'CEO' },
    gemini: { color: 'bg-emerald-600', label: 'CTO' },
    codex: { color: 'bg-orange-600', label: 'ENG' }
  };

  const c = configs[agent];

  return (
    <span className={`${c.color} px-2 py-0.5 rounded text-xs font-bold min-w-[40px] text-center`}>
      {c.label}
    </span>
  );
};

export default AITeamDashboard;
