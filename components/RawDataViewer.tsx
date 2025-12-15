import React, { useState, useEffect } from 'react';
import { Search, Database, ChevronDown, ChevronRight, AlertCircle, CheckCircle2 } from 'lucide-react';

interface RawDataViewerProps {
  patientId: string;
}

interface CacheSummary {
  patient: boolean;
  vitals: boolean;
  medications_count: number;
  problems_count: number;
  labs_count: number;
  allergies_count: number;
  notes_count: number;
  documents_count: number;
  unknown_count: number;
}

interface RawCacheResponse {
  patient_id: string;
  found_in_caches: string[];
  main_cache: Record<string, any> | null;
  active_fetch_cache: Record<string, any> | null;
  summary: CacheSummary;
  error?: string;
}

export const RawDataViewer: React.FC<RawDataViewerProps> = ({ patientId }) => {
  const [data, setData] = useState<RawCacheResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Record<string, any> | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['problems', 'medications']));

  const fetchRawCache = async () => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/active/raw-cache/${patientId}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error('Failed to fetch raw cache:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      const res = await fetch(`http://localhost:8000/active/search/${patientId}?q=${encodeURIComponent(searchQuery)}`);
      const json = await res.json();
      setSearchResults(json.matches);
    } catch (e) {
      console.error('Search failed:', e);
    }
  };

  useEffect(() => {
    if (patientId) {
      fetchRawCache();
    }
  }, [patientId]);

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const renderDataSection = (title: string, data: any, count?: number) => {
    const isExpanded = expandedSections.has(title.toLowerCase());
    const hasData = data && (Array.isArray(data) ? data.length > 0 : Object.keys(data).length > 0);

    return (
      <div key={title} className="border border-slate-700 rounded-lg mb-2 overflow-hidden">
        <button
          onClick={() => toggleSection(title.toLowerCase())}
          className="w-full flex items-center justify-between p-3 bg-slate-800 hover:bg-slate-750 text-left"
        >
          <div className="flex items-center gap-2">
            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span className="font-medium text-slate-200">{title}</span>
            {count !== undefined && (
              <span className={`text-xs px-2 py-0.5 rounded ${count > 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-600 text-slate-400'}`}>
                {count} items
              </span>
            )}
          </div>
          {hasData ? (
            <CheckCircle2 size={16} className="text-emerald-500" />
          ) : (
            <AlertCircle size={16} className="text-slate-500" />
          )}
        </button>
        {isExpanded && (
          <div className="p-3 bg-slate-900 max-h-64 overflow-y-auto">
            {hasData ? (
              <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono">
                {JSON.stringify(data, null, 2)}
              </pre>
            ) : (
              <p className="text-slate-500 text-sm italic">No data available</p>
            )}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
        <div className="animate-pulse text-slate-400">Loading raw cache data...</div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Database className="text-cyan-400" size={20} />
          <h3 className="text-lg font-semibold text-white">Raw Data Cache</h3>
        </div>
        <button
          onClick={fetchRawCache}
          className="text-xs px-3 py-1 bg-slate-800 hover:bg-slate-700 rounded text-slate-300"
        >
          Refresh
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex gap-2 mb-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search cached data (e.g., 'diabetes', 'aspirin', 'I10')..."
            className="w-full bg-slate-950 border border-slate-700 rounded pl-9 pr-3 py-2 text-sm text-slate-200"
          />
        </div>
        <button
          onClick={handleSearch}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded text-sm font-medium"
        >
          Search
        </button>
      </div>

      {/* Search Results */}
      {searchResults && (
        <div className="mb-4 p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
          <h4 className="text-sm font-semibold text-cyan-400 mb-2">
            Search Results for "{searchQuery}"
          </h4>
          {Object.keys(searchResults).length > 0 ? (
            Object.entries(searchResults).map(([category, matches]) => (
              <div key={category} className="mb-2">
                <span className="text-xs font-medium text-slate-300 uppercase">{category}:</span>
                <pre className="text-xs text-slate-400 mt-1 max-h-32 overflow-y-auto">
                  {JSON.stringify(matches, null, 2)}
                </pre>
              </div>
            ))
          ) : (
            <p className="text-slate-400 text-sm">No matches found</p>
          )}
        </div>
      )}

      {/* Summary Stats */}
      {data?.summary && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          {[
            { label: 'Problems', value: data.summary.problems_count, color: data.summary.problems_count > 0 ? 'emerald' : 'red' },
            { label: 'Medications', value: data.summary.medications_count, color: 'blue' },
            { label: 'Labs', value: data.summary.labs_count, color: 'purple' },
            { label: 'Allergies', value: data.summary.allergies_count, color: 'amber' },
          ].map(({ label, value, color }) => (
            <div key={label} className={`p-2 rounded bg-${color}-500/10 border border-${color}-500/30 text-center`}>
              <div className={`text-lg font-bold text-${color}-400`}>{value}</div>
              <div className="text-xs text-slate-400">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Data Sections */}
      {data?.main_cache && (
        <div className="space-y-1">
          {renderDataSection('Problems', data.main_cache.problems, data.summary?.problems_count)}
          {renderDataSection('Medications', data.main_cache.medications, data.summary?.medications_count)}
          {renderDataSection('Labs', data.main_cache.labs, data.summary?.labs_count)}
          {renderDataSection('Allergies', data.main_cache.allergies, data.summary?.allergies_count)}
          {renderDataSection('Vitals', data.main_cache.vitals)}
          {renderDataSection('Patient', data.main_cache.patient)}
          {renderDataSection('Notes', data.main_cache.notes, data.summary?.notes_count)}
          {renderDataSection('Unknown/Raw', data.main_cache.unknown, data.summary?.unknown_count)}
        </div>
      )}

      {data?.error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
          {data.error}
        </div>
      )}
    </div>
  );
};

export default RawDataViewer;
