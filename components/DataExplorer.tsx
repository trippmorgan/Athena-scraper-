import React, { useState, useEffect } from 'react';
import {
  FileText,
  FileImage,
  Activity,
  Pill,
  AlertTriangle,
  TestTube,
  Stethoscope,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Download,
  Eye,
  Search,
  Filter,
  Clock,
  User,
  Clipboard
} from 'lucide-react';

interface DataExplorerProps {
  patientId: string;
}

interface DataCategory {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  count: number;
  data: any[];
}

export const DataExplorer: React.FC<DataExplorerProps> = ({ patientId }) => {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [rawCache, setRawCache] = useState<any>(null);
  const [writeOps, setWriteOps] = useState<any[]>([]);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch patient cache
      const cacheRes = await fetch(`http://localhost:8000/active/raw-cache/${patientId}`);
      const cacheData = await cacheRes.json();
      setRawCache(cacheData);

      // Fetch write operations
      const writeRes = await fetch('http://localhost:8000/write-operations?limit=20');
      const writeData = await writeRes.json();
      setWriteOps(writeData.operations || []);
    } catch (e) {
      console.error('Failed to fetch data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (patientId) {
      fetchData();
    }
  }, [patientId]);

  const getCategories = (): DataCategory[] => {
    const cache = rawCache?.main_cache || {};

    return [
      {
        id: 'problems',
        label: 'Problems/Diagnoses',
        icon: <Stethoscope size={18} />,
        color: 'emerald',
        count: cache.problems?.length || 0,
        data: cache.problems || []
      },
      {
        id: 'medications',
        label: 'Medications',
        icon: <Pill size={18} />,
        color: 'blue',
        count: cache.medications?.length || 0,
        data: cache.medications || []
      },
      {
        id: 'labs',
        label: 'Lab Results',
        icon: <TestTube size={18} />,
        color: 'purple',
        count: cache.labs?.length || 0,
        data: cache.labs || []
      },
      {
        id: 'allergies',
        label: 'Allergies',
        icon: <AlertTriangle size={18} />,
        color: 'amber',
        count: cache.allergies?.length || 0,
        data: cache.allergies || []
      },
      {
        id: 'vitals',
        label: 'Vitals',
        icon: <Activity size={18} />,
        color: 'red',
        count: cache.vitals ? 1 : 0,
        data: cache.vitals ? [cache.vitals] : []
      },
      {
        id: 'notes',
        label: 'Clinical Notes',
        icon: <FileText size={18} />,
        color: 'cyan',
        count: cache.notes?.length || 0,
        data: cache.notes || []
      },
      {
        id: 'documents',
        label: 'Documents/PDFs',
        icon: <Clipboard size={18} />,
        color: 'indigo',
        count: cache.documents?.length || 0,
        data: cache.documents || []
      },
      {
        id: 'imaging',
        label: 'Imaging/Radiology',
        icon: <FileImage size={18} />,
        color: 'pink',
        count: cache.imaging?.length || 0,
        data: cache.imaging || []
      },
      {
        id: 'procedures',
        label: 'Procedures',
        icon: <Activity size={18} />,
        color: 'orange',
        count: cache.procedures?.length || 0,
        data: cache.procedures || []
      },
      {
        id: 'writes',
        label: 'Write Operations',
        icon: <Download size={18} />,
        color: 'yellow',
        count: writeOps.length,
        data: writeOps
      }
    ];
  };

  const categories = getCategories();
  const totalItems = categories.reduce((sum, cat) => sum + cat.count, 0);

  const toggleItem = (id: string) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedItems(newExpanded);
  };

  const filteredCategories = activeTab === 'all'
    ? categories
    : categories.filter(c => c.id === activeTab);

  const renderDataItem = (item: any, index: number, categoryId: string) => {
    const itemId = `${categoryId}-${index}`;
    const isExpanded = expandedItems.has(itemId);

    // Extract display info based on data type
    let title = '';
    let subtitle = '';
    let date = '';

    if (categoryId === 'problems') {
      title = item.description || item.name || item.display || 'Unknown Problem';
      subtitle = item.icd10Code || item.code || '';
      date = item.onsetDate || item.startDate || '';
    } else if (categoryId === 'medications') {
      title = item.name || item.medicationName || item.drugName || 'Unknown Medication';
      subtitle = item.dose || item.dosage || '';
      date = item.startDate || item.prescribedDate || '';
    } else if (categoryId === 'labs') {
      title = item.name || item.testName || 'Unknown Lab';
      subtitle = `${item.value || item.result || ''} ${item.unit || ''}`;
      date = item.date || item.resultDate || '';
    } else if (categoryId === 'allergies') {
      title = item.allergen || item.name || item.substance || 'Unknown Allergen';
      subtitle = item.reaction || item.manifestation || '';
      date = '';
    } else if (categoryId === 'notes') {
      title = item.title || item.noteType || item.type || 'Clinical Note';
      subtitle = item.author || item.provider || '';
      date = item.date || item.createdDate || '';
    } else if (categoryId === 'writes') {
      title = `${item.method} ${(item.url || '').split('/').slice(-2).join('/')}`;
      subtitle = item.patient_id ? `Patient: ${item.patient_id}` : '';
      date = item.timestamp || '';
    } else {
      title = item.name || item.title || item.description || `Item ${index + 1}`;
      subtitle = item.type || item.category || '';
      date = item.date || '';
    }

    return (
      <div key={itemId} className="border border-slate-700 rounded-lg mb-2 overflow-hidden">
        <button
          onClick={() => toggleItem(itemId)}
          className="w-full flex items-center justify-between p-3 bg-slate-800/50 hover:bg-slate-800 text-left"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="text-sm font-medium text-slate-200 truncate">{title}</span>
            </div>
            {subtitle && (
              <span className="text-xs text-slate-400 ml-6">{subtitle}</span>
            )}
          </div>
          {date && (
            <div className="flex items-center gap-1 text-xs text-slate-500">
              <Clock size={12} />
              {date}
            </div>
          )}
        </button>
        {isExpanded && (
          <div className="p-3 bg-slate-900 border-t border-slate-700">
            <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono overflow-x-auto">
              {JSON.stringify(item, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
        <div className="flex items-center gap-3">
          <RefreshCw className="animate-spin text-cyan-400" size={20} />
          <span className="text-slate-400">Loading patient data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-700 bg-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Eye className="text-cyan-400" size={20} />
            <h3 className="text-lg font-semibold text-white">Data Explorer</h3>
            <span className="text-xs px-2 py-0.5 bg-slate-700 rounded text-slate-300">
              {totalItems} items
            </span>
          </div>
          <button
            onClick={fetchData}
            className="flex items-center gap-1 text-xs px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search all data..."
            className="w-full bg-slate-950 border border-slate-700 rounded pl-9 pr-3 py-2 text-sm text-slate-200"
          />
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex flex-wrap gap-1 p-2 border-b border-slate-700 bg-slate-800/30">
        <button
          onClick={() => setActiveTab('all')}
          className={`px-3 py-1.5 text-xs rounded font-medium transition-colors ${
            activeTab === 'all'
              ? 'bg-cyan-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
        >
          All ({totalItems})
        </button>
        {categories.map(cat => (
          <button
            key={cat.id}
            onClick={() => setActiveTab(cat.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded font-medium transition-colors ${
              activeTab === cat.id
                ? `bg-${cat.color}-600 text-white`
                : `bg-slate-700 text-slate-300 hover:bg-slate-600 ${cat.count === 0 ? 'opacity-50' : ''}`
            }`}
          >
            {cat.icon}
            {cat.label}
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${
              activeTab === cat.id ? 'bg-white/20' : 'bg-slate-600'
            }`}>
              {cat.count}
            </span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 max-h-[600px] overflow-y-auto">
        {filteredCategories.map(category => (
          <div key={category.id} className="mb-6 last:mb-0">
            <div className="flex items-center gap-2 mb-3">
              <div className={`text-${category.color}-400`}>{category.icon}</div>
              <h4 className="text-sm font-semibold text-slate-200">{category.label}</h4>
              <span className={`text-xs px-2 py-0.5 rounded bg-${category.color}-500/20 text-${category.color}-400`}>
                {category.count} items
              </span>
            </div>

            {category.count === 0 ? (
              <div className="text-center py-6 text-slate-500 text-sm border border-dashed border-slate-700 rounded-lg">
                No {category.label.toLowerCase()} data available
              </div>
            ) : (
              <div className="space-y-1">
                {category.data
                  .filter(item => {
                    if (!searchQuery) return true;
                    return JSON.stringify(item).toLowerCase().includes(searchQuery.toLowerCase());
                  })
                  .map((item, idx) => renderDataItem(item, idx, category.id))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Patient Info Footer */}
      {rawCache?.main_cache?.patient && (
        <div className="p-3 border-t border-slate-700 bg-slate-800/30">
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <div className="flex items-center gap-1">
              <User size={14} />
              <span>Patient ID: {patientId}</span>
            </div>
            {rawCache.main_cache.patient.name && (
              <span>Name: {rawCache.main_cache.patient.name?.full || rawCache.main_cache.patient.name}</span>
            )}
            {rawCache.main_cache.patient.birthDate && (
              <span>DOB: {rawCache.main_cache.patient.birthDate}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DataExplorer;
