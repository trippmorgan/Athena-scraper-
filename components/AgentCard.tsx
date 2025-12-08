import React from 'react';
import { AgentOutput } from '../types';
import { Bot, Loader2, Sparkles, AlertTriangle } from 'lucide-react';

interface AgentCardProps {
  output: AgentOutput;
  icon?: React.ReactNode;
  colorClass?: string;
}

export const AgentCard: React.FC<AgentCardProps> = ({ output, icon, colorClass = "border-slate-700" }) => {
  return (
    <div className={`bg-slate-900 border ${colorClass} rounded-lg p-4 flex flex-col h-full relative overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-cyan-900/10`}>
      <div className="flex justify-between items-center mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-slate-800 rounded-md text-slate-200">
            {icon || <Bot size={16} />}
          </div>
          <h3 className="font-semibold text-sm tracking-wide text-slate-100">{output.agentName}</h3>
        </div>
        {output.status === 'thinking' && (
          <div className="flex items-center gap-1 text-xs text-cyan-400">
            <Loader2 size={12} className="animate-spin" />
            <span>Processing</span>
          </div>
        )}
        {output.status === 'complete' && (
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <Sparkles size={12} />
            <span>{output.modelUsed}</span>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto text-sm text-slate-300 leading-relaxed font-mono whitespace-pre-wrap">
        {output.content || <span className="text-slate-600 italic">Waiting for data stream...</span>}
      </div>

      {/* Decorative background element */}
      <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
        <Bot size={64} />
      </div>
    </div>
  );
};
