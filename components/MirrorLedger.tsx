import React from 'react';
import { LedgerEntry } from '../types';
import { ShieldCheck, Database, Link } from 'lucide-react';

interface MirrorLedgerProps {
  entries: LedgerEntry[];
}

export const MirrorLedger: React.FC<MirrorLedgerProps> = ({ entries }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4 text-slate-400 border-b border-slate-800 pb-2">
        <ShieldCheck size={16} className="text-emerald-500" />
        <span className="uppercase text-xs font-bold tracking-widest">Mirror Ledger (Audit)</span>
      </div>
      
      <div className="flex-1 relative pl-4 border-l border-slate-800 space-y-6 overflow-y-auto">
        {entries.map((entry) => (
          <div key={entry.hash} className="relative group">
            {/* Timeline Dot */}
            <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-slate-700 border-2 border-slate-900 group-hover:bg-cyan-500 transition-colors"></div>
            
            <div className="flex flex-col gap-1">
              <span className="text-[10px] text-slate-500 font-mono">{entry.timestamp.split('T')[1].replace('Z','')}</span>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-200">{entry.entity}</span>
                <span className="text-[10px] text-slate-500 px-1 border border-slate-700 rounded bg-slate-800 font-mono">
                  {entry.hash.substring(0, 8)}
                </span>
              </div>
              <span className="text-xs text-slate-400">{entry.action}</span>
            </div>
          </div>
        ))}
        {entries.length === 0 && <span className="text-xs text-slate-600 italic">Ledger initialized. No blocks mined.</span>}
      </div>
      
      <div className="mt-2 pt-2 border-t border-slate-800 flex justify-between items-center text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <Database size={10} />
          <span>PostgreSQL (PlaudAI)</span>
        </div>
        <div className="flex items-center gap-1">
          <Link size={10} />
          <span>Synced</span>
        </div>
      </div>
    </div>
  );
};
