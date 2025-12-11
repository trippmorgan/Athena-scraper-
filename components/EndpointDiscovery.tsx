import React, { useState, useCallback, useEffect } from 'react';
import { Upload, Search, Zap, Check, AlertCircle, Loader2, Copy, Download } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

interface DiscoveredEndpoint {
  pattern: string;
  confidence: 'high' | 'medium' | 'low';
  description: string;
  category: string;
  dataType?: string;
}

interface DiscoveryResponse {
  success: boolean;
  endpoints: DiscoveredEndpoint[];
  recommended_config: string[];
  reasoning: string;
  timestamp: string;
}

interface ServiceStatus {
  service: string;
  status: string;
  model_id: string | null;
}

export default function EndpointDiscovery() {
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generatedConfig, setGeneratedConfig] = useState<string | null>(null);
  const [trafficLog, setTrafficLog] = useState<any[]>([]);
  const [isRecording, setIsRecording] = useState(false);

  // Check service status on mount
  useEffect(() => {
    fetch(`${API_BASE}/discovery/status`)
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus({ service: 'Vision Discovery', status: 'offline', model_id: null }));
  }, []);

  // Screenshot upload handler
  const handleScreenshotUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsAnalyzing(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/discovery/analyze-screenshot`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: DiscoveryResponse = await response.json();
      setResult(data);

      if (data.success && data.endpoints.length > 0) {
        await generateConfig(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  // Traffic log analysis
  const analyzeTrafficLog = useCallback(async () => {
    if (trafficLog.length === 0) {
      setError('No traffic captured. Start recording first.');
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    // Aggregate traffic into report format
    const endpointMap = new Map<string, { count: number; methods: Set<string>; sizes: number[] }>();
    
    trafficLog.forEach(entry => {
      const key = entry.url;
      if (!endpointMap.has(key)) {
        endpointMap.set(key, { count: 0, methods: new Set(), sizes: [] });
      }
      const ep = endpointMap.get(key)!;
      ep.count++;
      ep.methods.add(entry.method || 'GET');
      ep.sizes.push(entry.size || 0);
    });

    const report = {
      duration: 60,
      totalRequests: trafficLog.length,
      uniqueEndpoints: endpointMap.size,
      endpoints: Array.from(endpointMap.entries()).map(([path, data]) => ({
        path,
        count: data.count,
        methods: Array.from(data.methods),
        avgSize: Math.round(data.sizes.reduce((a, b) => a + b, 0) / data.sizes.length)
      }))
    };

    try {
      const response = await fetch(`${API_BASE}/discovery/analyze-traffic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report)
      });

      const data: DiscoveryResponse = await response.json();
      setResult(data);

      if (data.success && data.endpoints.length > 0) {
        await generateConfig(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Traffic analysis failed');
    } finally {
      setIsAnalyzing(false);
    }
  }, [trafficLog]);

  // Generate interceptor config
  const generateConfig = async (analysis: DiscoveryResponse) => {
    try {
      const response = await fetch(`${API_BASE}/discovery/generate-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(analysis)
      });

      const data = await response.json();
      setGeneratedConfig(data.javascript);
    } catch (err) {
      console.error('Config generation failed:', err);
    }
  };

  // Listen for traffic from extension
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'ATHENA_TRAFFIC' && isRecording) {
        setTrafficLog(prev => [...prev, event.data.payload]);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [isRecording]);

  const copyConfig = () => {
    if (generatedConfig) {
      navigator.clipboard.writeText(generatedConfig);
    }
  };

  const downloadConfig = () => {
    if (generatedConfig) {
      const blob = new Blob([generatedConfig], { type: 'text/javascript' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'interceptor-config.js';
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const confidenceColor = (c: string) => {
    switch (c) {
      case 'high': return 'text-green-400 bg-green-400/10';
      case 'medium': return 'text-yellow-400 bg-yellow-400/10';
      case 'low': return 'text-red-400 bg-red-400/10';
      default: return 'text-gray-400 bg-gray-400/10';
    }
  };

  return (
    <div className="bg-gray-900 text-gray-100 p-6 rounded-lg space-y-6">
      {/* Header + Status */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Search className="w-5 h-5 text-blue-400" />
          Endpoint Discovery
        </h2>
        <div className={`px-3 py-1 rounded-full text-sm ${
          status?.status === 'online' ? 'bg-green-500/20 text-green-400' :
          status?.status === 'degraded (heuristic_only)' ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-red-500/20 text-red-400'
        }`}>
          {status?.status || 'checking...'}
        </div>
      </div>

      {/* Input Methods */}
      <div className="grid grid-cols-2 gap-4">
        {/* Screenshot Upload */}
        <div className="border border-gray-700 rounded-lg p-4 space-y-3">
          <h3 className="font-medium flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Screenshot Analysis
          </h3>
          <p className="text-sm text-gray-400">
            Upload a DevTools Network tab screenshot
          </p>
          <label className="block">
            <input
              type="file"
              accept="image/*"
              onChange={handleScreenshotUpload}
              disabled={isAnalyzing}
              className="hidden"
            />
            <div className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center cursor-pointer hover:border-blue-500 transition-colors">
              {isAnalyzing ? (
                <Loader2 className="w-8 h-8 mx-auto animate-spin text-blue-400" />
              ) : (
                <>
                  <Upload className="w-8 h-8 mx-auto text-gray-500 mb-2" />
                  <span className="text-sm text-gray-400">Click or drag to upload</span>
                </>
              )}
            </div>
          </label>
        </div>

        {/* Traffic Recording */}
        <div className="border border-gray-700 rounded-lg p-4 space-y-3">
          <h3 className="font-medium flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Live Traffic Analysis
          </h3>
          <p className="text-sm text-gray-400">
            Record network traffic, then analyze patterns
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setIsRecording(!isRecording);
                if (!isRecording) setTrafficLog([]);
              }}
              className={`flex-1 py-2 rounded-lg font-medium transition-colors ${
                isRecording 
                  ? 'bg-red-500 hover:bg-red-600' 
                  : 'bg-blue-500 hover:bg-blue-600'
              }`}
            >
              {isRecording ? 'Stop Recording' : 'Start Recording'}
            </button>
            <button
              onClick={analyzeTrafficLog}
              disabled={trafficLog.length === 0 || isAnalyzing}
              className="flex-1 py-2 rounded-lg font-medium bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Analyze ({trafficLog.length})
            </button>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-red-400">Analysis Error</p>
            <p className="text-sm text-gray-400">{error}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Discovered Endpoints ({result.endpoints.length})</h3>
            {result.success && <Check className="w-5 h-5 text-green-400" />}
          </div>

          {/* Reasoning */}
          <div className="bg-gray-800 rounded-lg p-3 text-sm text-gray-300">
            <span className="text-gray-500">Analysis: </span>
            {result.reasoning}
          </div>

          {/* Endpoint List */}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {result.endpoints.map((ep, i) => (
              <div key={i} className="bg-gray-800 rounded-lg p-3 flex items-start justify-between">
                <div>
                  <code className="text-blue-400 text-sm">{ep.pattern}</code>
                  <p className="text-xs text-gray-400 mt-1">{ep.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  {ep.dataType && (
                    <span className="px-2 py-0.5 rounded text-xs bg-purple-500/20 text-purple-400">
                      {ep.dataType}
                    </span>
                  )}
                  <span className={`px-2 py-0.5 rounded text-xs ${confidenceColor(ep.confidence)}`}>
                    {ep.confidence}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Generated Config */}
      {generatedConfig && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Generated Configuration</h3>
            <div className="flex gap-2">
              <button onClick={copyConfig} className="p-2 hover:bg-gray-700 rounded">
                <Copy className="w-4 h-4" />
              </button>
              <button onClick={downloadConfig} className="p-2 hover:bg-gray-700 rounded">
                <Download className="w-4 h-4" />
              </button>
            </div>
          </div>
          <pre className="bg-gray-950 rounded-lg p-4 text-xs overflow-x-auto max-h-48 overflow-y-auto">
            {generatedConfig}
          </pre>
        </div>
      )}
    </div>
  );
}