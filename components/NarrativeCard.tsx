import React, { useState } from 'react';
import { Sparkles, Eye, Copy, RefreshCw, FileText, ShieldCheck, AlertTriangle } from 'lucide-react';

interface NarrativeProps {
  patientId: string;
  onGenerate?: () => void;
}

export const NarrativeCard: React.FC<NarrativeProps> = ({ patientId }) => {
  const [narrative, setNarrative] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [useVision, setUseVision] = useState(false);
  const [sources, setSources] = useState<string[]>([]);
  const [quality, setQuality] = useState<number>(0);
  const [copied, setCopied] = useState(false);

  const generateNarrative = async () => {
    setLoading(true);
    setCopied(false);
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
        setQuality(data.data_quality_score || 0);
      } else if (data.error) {
        setNarrative(`Error: ${data.error}`);
        setQuality(0);
      }
    } catch (e) {
      console.error("Narrative gen failed", e);
      setNarrative("Failed to generate narrative. Ensure backend is running.");
      setQuality(0);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(narrative);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getQualityColor = (score: number) => {
    if (score >= 0.7) return 'text-emerald-400';
    if (score >= 0.4) return 'text-amber-400';
    return 'text-red-400';
  };

  const getQualityLabel = (score: number) => {
    if (score >= 0.7) return 'High';
    if (score >= 0.4) return 'Medium';
    return 'Low';
  };

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 mb-6 shadow-lg shadow-black/40">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/20 rounded-lg border border-indigo-500/30">
            <Sparkles className="text-indigo-400" size={20} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              Clinical Narrative
              {quality >= 0.7 && narrative && (
                <ShieldCheck size={14} className="text-emerald-500" title="High Data Quality" />
              )}
              {quality > 0 && quality < 0.4 && narrative && (
                <AlertTriangle size={14} className="text-amber-500" title="Low Data Quality" />
              )}
            </h3>
            <p className="text-xs text-slate-400">AI-Synthesized from Sorted Data</p>
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
            <span>Include Documents</span>
          </label>

          <button
            onClick={generateNarrative}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white text-sm font-medium rounded-lg transition-all shadow-md shadow-indigo-900/20"
          >
            {loading ? <RefreshCw className="animate-spin" size={16} /> : <FileText size={16} />}
            {loading ? "Sorting & Writing..." : "Generate"}
          </button>
        </div>
      </div>

      <div className="relative group min-h-[100px] bg-slate-950/50 rounded-lg border border-slate-800 p-5">
        {narrative ? (
          <>
            <p className="text-slate-200 text-base leading-7 font-serif tracking-wide">
              {narrative}
            </p>
            <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={copyToClipboard}
                className={`p-2 rounded text-sm transition-colors ${
                  copied
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white'
                }`}
                title={copied ? "Copied!" : "Copy to Clipboard"}
              >
                <Copy size={14} />
              </button>
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 italic text-sm py-8">
            <Sparkles size={24} className="mb-2 opacity-20" />
            <span>Click "Generate" to sort data and write narrative.</span>
          </div>
        )}
      </div>

      {/* Quality Score & Sources */}
      {narrative && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <div className="flex justify-between items-start">
            {/* Data Quality */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-bold text-slate-500">Data Quality:</span>
              <span className={`text-xs font-semibold ${getQualityColor(quality)}`}>
                {getQualityLabel(quality)} ({Math.round(quality * 100)}%)
              </span>
            </div>

            {/* Sources */}
            {sources.length > 0 && (
              <div className="flex flex-wrap gap-2 justify-end">
                {sources.map((src, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-slate-800 rounded text-[10px] text-slate-400 border border-slate-700/50 flex items-center gap-1"
                  >
                    {src.includes("Vision") || src.includes("Doc") ? <Eye size={8} /> : <FileText size={8} />}
                    {src}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NarrativeCard;
