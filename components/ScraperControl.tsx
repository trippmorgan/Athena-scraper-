import React from 'react';
import { ScraperMode, ScraperStatus } from '../types';
import { Radio, Activity, Zap } from 'lucide-react';

interface ScraperControlProps {
  mode: ScraperMode;
  status: ScraperStatus;
  onModeChange: (mode: ScraperMode) => void;
}

export const ScraperControl: React.FC<ScraperControlProps> = ({ mode, status, onModeChange }) => {
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-1 flex items-center gap-1 relative">
      <button
        onClick={() => onModeChange(ScraperMode.PASSIVE)}
        className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded text-sm font-medium transition-all ${
          mode === ScraperMode.PASSIVE 
            ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-600' 
            : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
        }`}
      >
        <Radio size={16} />
        <div className="flex flex-col items-start leading-none">
          <span>Passive</span>
          <span className="text-[10px] opacity-70 font-normal">Interceptor</span>
        </div>
      </button>

      <button
        onClick={() => onModeChange(ScraperMode.ACTIVE)}
        className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded text-sm font-medium transition-all ${
          mode === ScraperMode.ACTIVE 
            ? 'bg-slate-800 text-amber-500 shadow-sm border border-slate-600' 
            : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
        }`}
      >
        <Zap size={16} />
        <div className="flex flex-col items-start leading-none">
          <span>Active</span>
          <span className="text-[10px] opacity-70 font-normal">Vacuum Mode</span>
        </div>
      </button>

      {/* Status Indicator */}
      <div className="absolute -top-1 -right-1">
         <span className={`flex h-3 w-3 ${status === ScraperStatus.INTERCEPTING || status === ScraperStatus.CRAWLING ? '' : 'hidden'}`}>
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${mode === ScraperMode.ACTIVE ? 'bg-amber-500' : 'bg-green-500'}`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${mode === ScraperMode.ACTIVE ? 'bg-amber-500' : 'bg-green-500'}`}></span>
          </span>
      </div>
    </div>
  );
};
