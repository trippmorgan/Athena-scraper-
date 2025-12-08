import React, { useEffect, useRef } from 'react';
import { LogEntry, ScraperStatus } from '../types';
import { Terminal, Wifi } from 'lucide-react';

interface LiveLogProps {
  logs: LogEntry[];
  status: ScraperStatus;
}

export const LiveLog: React.FC<LiveLogProps> = ({ logs, status }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg h-full flex flex-col font-mono text-xs overflow-hidden shadow-inner shadow-black/50">
      <div className="bg-slate-950 p-2 border-b border-slate-800 flex justify-between items-center">
        <div className="flex items-center gap-2 text-slate-400">
          <Terminal size={14} />
          <span className="uppercase tracking-wider font-bold">Interceptor Log</span>
        </div>
        <div className={`flex items-center gap-2 ${status === ScraperStatus.INTERCEPTING ? 'text-green-500' : 'text-amber-500'}`}>
          <Wifi size={14} className={status === ScraperStatus.INTERCEPTING ? 'animate-pulse' : ''} />
          <span>{status}</span>
        </div>
      </div>
      
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-2 space-y-1">
        {logs.length === 0 && (
          <div className="text-slate-600 text-center mt-10">Waiting for AthenaNet traffic...</div>
        )}
        {logs.map((log) => (
          <div key={log.id} className="flex gap-2 hover:bg-slate-800 p-1 rounded transition-colors cursor-default group">
            <span className="text-slate-500 w-16 shrink-0">{log.timestamp.split('T')[1].split('.')[0]}</span>
            <span className={`w-10 shrink-0 font-bold ${log.method === 'GET' ? 'text-cyan-400' : 'text-purple-400'}`}>
              {log.method}
            </span>
            <span className="text-slate-300 truncate flex-1 group-hover:text-white transition-colors">
              {log.endpoint}
            </span>
            <span className="text-emerald-500 w-12 text-right">{log.status}</span>
            <span className="text-slate-600 w-12 text-right">{log.size}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
