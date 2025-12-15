import React, { useState } from 'react';
import { Sparkles, Eye, Copy, RefreshCw, FileText } from 'lucide-react';

interface NarrativeProps {
  patientId: string;
  onGenerate?: () => void;
}

export const NarrativeCard: React.FC<NarrativeProps> = ({ patientId }) => {
  const [narrative, setNarrative] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [useVision, setUseVision] = useState(false);
  const [sources, setSources] = useState<string[]>([]);

  const generateNarrative = async () => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/ai/narrative/${patientId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_vision: useVision })
      });
      const data = await res.json();
      if (data.narrative) {
        setNarrative(data.narrative);
        setSources(data.sources_used || []);
      }
    } catch (e) {
      console.error("Narrative gen failed", e);
      setNarrative("Failed to generate narrative. Ensure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(narrative);
  };

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 mb-6 shadow-lg shadow-black/40">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-indigo-500/20 rounded-lg">
            <Sparkles className="text-indigo-400" size={20} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Clinical Narrative</h3>
            <p className="text-xs text-slate-400">AI-Synthesized Summary</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer hover:text-white transition-colors">
            <input 
              type="checkbox" 
              checked={useVision}
              onChange={(e) => setUseVision(e.target.checked)}
              className="rounded bg-slate-800 border-slate-600 text-indigo-500 focus:ring-0"
            />
            <Eye size={14} className={useVision ? "text-indigo-400" : ""} />
            <span>Read Documents (Vision)</span>
          </label>
          
          <button 
            onClick={generateNarrative}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white text-sm font-medium rounded-lg transition-all"
          >
            {loading ? <RefreshCw className="animate-spin" size={16} /> : <FileText size={16} />}
            {loading ? "Synthesizing..." : "Generate"}
          </button>
        </div>
      </div>

      <div className="relative group min-h-[100px] bg-slate-950/50 rounded-lg border border-slate-800 p-4">
        {narrative ? (
          <>
            <p className="text-slate-200 text-base leading-relaxed font-serif tracking-wide">
              {narrative}
            </p>
            <button 
              onClick={copyToClipboard}
              className="absolute top-2 right-2 p-2 bg-slate-800 hover:bg-slate-700 rounded text-slate-400 hover:text-white opacity-0 group-hover:opacity-100 transition-all"
              title="Copy to Clipboard"
            >
              <Copy size={14} />
            </button>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 italic text-sm">
            <span>Click "Generate" to synthesize a narrative from gathered data.</span>
          </div>
        )}
      </div>

      {sources.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {sources.map((src, i) => (
            <span key={i} className="px-2 py-1 bg-slate-800 rounded text-[10px] text-slate-500 border border-slate-700/50">
              {src}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};