import React, { useState, useEffect } from 'react';
import { 
  Search, AlertTriangle, CheckCircle2, XCircle, Clock, 
  Pill, Heart, Droplets, FileText, Activity, Syringe,
  AlertOctagon, Stethoscope, Scissors, ClipboardList
} from 'lucide-react';

// Types
interface AntithromboticMed {
  name: string;
  dose?: string;
  category: string;
  hold_days_preop: number;
  bridging_required: boolean;
  reversal_agent?: string;
}

interface VascularProfile {
  patient_id: string;
  mrn: string;
  name: string;
  antithrombotics: AntithromboticMed[];
  renal_function?: {
    creatinine?: number;
    egfr?: number;
    contrast_risk: string;
  };
  coagulation?: {
    inr?: number;
    pt?: number;
    ptt?: number;
    reversal_needed: boolean;
  };
  cardiac_clearance?: {
    cleared?: boolean;
    ejection_fraction?: number;
    stress_test_result?: string;
  };
  critical_allergies: Array<{
    allergen: string;
    surgical_implication?: string;
  }>;
  vascular_history: Array<{
    procedure: string;
    date?: string;
    location?: string;
  }>;
  high_bleeding_risk: boolean;
  contrast_caution: boolean;
  cardiac_risk: string;
}

interface PreOpChecklist {
  patient_id: string;
  mrn: string;
  name: string;
  antithrombotics_held: boolean;
  anticoagulant_details: string;
  bridging_required: boolean;
  renal_function_ok: boolean;
  renal_details: string;
  coagulation_ok: boolean;
  coagulation_details: string;
  cardiac_cleared: boolean;
  cardiac_details: string;
  contrast_allergy: boolean;
  allergy_alerts: string[];
  ready_for_surgery: boolean;
  blocking_issues: string[];
}

type SurgicalPhase = 'preop' | 'intraop' | 'postop';

interface SurgicalDashboardProps {
  onSearch?: (mrn: string) => void;
}

const API_BASE = 'http://localhost:8000';

export const SurgicalDashboard: React.FC<SurgicalDashboardProps> = ({ onSearch }) => {
  const [mrn, setMrn] = useState('');
  const [loading, setLoading] = useState(false);
  const [activePhase, setActivePhase] = useState<SurgicalPhase>('preop');
  const [profile, setProfile] = useState<VascularProfile | null>(null);
  const [checklist, setChecklist] = useState<PreOpChecklist | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = async (patientId: string): Promise<VascularProfile | null> => {
    try {
      const res = await fetch(`${API_BASE}/active/profile/${patientId}`);
      const data = await res.json();
      console.log('Profile response:', data);
      if (data.success && data.profile) {
        setProfile(data.profile);
        return data.profile;
      }
      return null;
    } catch (e) {
      console.error('Failed to fetch profile:', e);
      return null;
    }
  };

  const fetchChecklist = async (patientId: string): Promise<PreOpChecklist | null> => {
    try {
      const res = await fetch(`${API_BASE}/active/preop-checklist/${patientId}`);
      if (res.ok) {
        const data = await res.json();
        console.log('Checklist response:', data);
        setChecklist(data);
        return data;
      }
      return null;
    } catch (e) {
      console.error('Failed to fetch checklist:', e);
      return null;
    }
  };

  const handleSearch = async () => {
    if (!mrn.trim()) return;

    setLoading(true);
    setError(null);
    setProfile(null);
    setChecklist(null);

    try {
      // Trigger active fetch via extension (if available)
      if (onSearch) {
        onSearch(mrn);
      }

      // Poll for profile data with retries
      let attempts = 0;
      const maxAttempts = 10;
      const pollInterval = 1000;
      let foundProfile: VascularProfile | null = null;

      const pollForData = async (): Promise<void> => {
        attempts++;
        console.log(`Poll attempt ${attempts}/${maxAttempts} for MRN: ${mrn}`);

        foundProfile = await fetchProfile(mrn);
        await fetchChecklist(mrn);

        // Check the RETURNED value, not stale state
        if (foundProfile || attempts >= maxAttempts) {
          setLoading(false);
          if (!foundProfile && attempts >= maxAttempts) {
            setError('No profile found. Navigate to patient chart in Athena first, then try again.');
          }
        } else {
          // Keep polling
          setTimeout(pollForData, pollInterval);
        }
      };

      await pollForData();
    } catch (e) {
      setError('Failed to fetch patient data');
      setLoading(false);
    }
  };

  const StatusIcon = ({ ok }: { ok: boolean }) => (
    ok ? <CheckCircle2 className="text-emerald-500" size={18} /> 
       : <XCircle className="text-red-500" size={18} />
  );

  const RiskBadge = ({ level }: { level: string }) => {
    const colors: Record<string, string> = {
      low: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
      moderate: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
      high: 'bg-red-500/20 text-red-400 border-red-500/30',
      contraindicated: 'bg-red-600/30 text-red-300 border-red-500/50',
      cleared: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
      unknown: 'bg-slate-500/20 text-slate-400 border-slate-500/30'
    };
    return (
      <span className={`px-2 py-0.5 text-xs rounded border ${colors[level] || colors.unknown}`}>
        {level.toUpperCase()}
      </span>
    );
  };

  return (
    <div className="h-full flex flex-col bg-slate-950 text-slate-200">
      {/* Search Header */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/50">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
            <input
              type="text"
              value={mrn}
              onChange={(e) => setMrn(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Enter MRN for active fetch..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg py-2.5 pl-10 pr-4 text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 rounded-lg font-medium transition-colors"
          >
            {loading ? 'Fetching...' : 'Fetch Patient'}
          </button>
        </div>

        {/* Phase Tabs */}
        <div className="flex gap-2 mt-4">
          {(['preop', 'intraop', 'postop'] as SurgicalPhase[]).map((phase) => (
            <button
              key={phase}
              onClick={() => setActivePhase(phase)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activePhase === phase
                  ? 'bg-cyan-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {phase === 'preop' && <ClipboardList size={16} />}
              {phase === 'intraop' && <Scissors size={16} />}
              {phase === 'postop' && <Activity size={16} />}
              {phase === 'preop' ? 'Pre-Op' : phase === 'intraop' ? 'Intra-Op' : 'Post-Op'}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="mb-4 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
            {error}
          </div>
        )}

        {!profile && !loading && (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500">
            <Stethoscope size={48} className="mb-4 opacity-50" />
            <p>Enter an MRN to fetch patient data</p>
            <p className="text-sm mt-2">Requires active Athena session</p>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-cyan-500 border-t-transparent"></div>
            <p className="mt-4 text-slate-400">Fetching patient data from Athena...</p>
          </div>
        )}

        {/* PRE-OP VIEW */}
        {profile && activePhase === 'preop' && (
          <div className="space-y-4">
            {/* Patient Header */}
            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-xl font-semibold text-white">{profile.name}</h2>
                  <p className="text-slate-400 font-mono">{profile.mrn}</p>
                </div>
                <div className="flex gap-2">
                  {profile.high_bleeding_risk && (
                    <span className="px-3 py-1 bg-red-500/20 text-red-400 rounded-full text-sm flex items-center gap-1">
                      <Droplets size={14} /> Bleeding Risk
                    </span>
                  )}
                  {profile.contrast_caution && (
                    <span className="px-3 py-1 bg-amber-500/20 text-amber-400 rounded-full text-sm flex items-center gap-1">
                      <AlertTriangle size={14} /> Contrast Caution
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Checklist Status */}
            {checklist && (
              <div className={`p-4 rounded-lg border ${
                checklist.ready_for_surgery 
                  ? 'bg-emerald-500/10 border-emerald-500/30' 
                  : 'bg-red-500/10 border-red-500/30'
              }`}>
                <div className="flex items-center gap-3">
                  {checklist.ready_for_surgery 
                    ? <CheckCircle2 className="text-emerald-500" size={24} />
                    : <AlertOctagon className="text-red-500" size={24} />
                  }
                  <div>
                    <p className={`font-semibold ${checklist.ready_for_surgery ? 'text-emerald-400' : 'text-red-400'}`}>
                      {checklist.ready_for_surgery ? 'Ready for Surgery' : 'Not Cleared'}
                    </p>
                    {checklist.blocking_issues.length > 0 && (
                      <p className="text-sm text-slate-400">
                        {checklist.blocking_issues.join(' • ')}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Antithrombotics */}
            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                <Pill size={16} className="text-purple-400" />
                ANTITHROMBOTIC STATUS
              </h3>
              {profile.antithrombotics.length > 0 ? (
                <div className="space-y-2">
                  {profile.antithrombotics.map((med, i) => (
                    <div key={i} className="flex justify-between items-center p-3 bg-slate-800/50 rounded-lg">
                      <div>
                        <span className="font-medium text-white">{med.name}</span>
                        {med.dose && <span className="text-slate-400 ml-2">{med.dose}</span>}
                        <span className="ml-2 px-2 py-0.5 text-xs bg-slate-700 rounded text-slate-300">
                          {med.category}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-amber-400 text-sm">Hold {med.hold_days_preop} days</span>
                        {med.bridging_required && (
                          <span className="block text-xs text-red-400">Bridging required</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500">No antithrombotics on record</p>
              )}
            </div>

            {/* Labs Grid */}
            <div className="grid grid-cols-2 gap-4">
              {/* Renal Function */}
              <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                  <Syringe size={16} className="text-blue-400" />
                  RENAL FUNCTION
                </h3>
                {profile.renal_function ? (
                  <div className="space-y-2">
                    {profile.renal_function.creatinine && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">Creatinine</span>
                        <span className="text-white">{profile.renal_function.creatinine}</span>
                      </div>
                    )}
                    {profile.renal_function.egfr && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">eGFR</span>
                        <span className="text-white">{profile.renal_function.egfr}</span>
                      </div>
                    )}
                    <div className="flex justify-between items-center pt-2 border-t border-slate-700">
                      <span className="text-slate-400">Contrast Risk</span>
                      <RiskBadge level={profile.renal_function.contrast_risk} />
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-500">No recent labs</p>
                )}
              </div>

              {/* Coagulation */}
              <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                  <Droplets size={16} className="text-red-400" />
                  COAGULATION
                </h3>
                {profile.coagulation ? (
                  <div className="space-y-2">
                    {profile.coagulation.inr && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">INR</span>
                        <span className={profile.coagulation.inr > 1.5 ? 'text-red-400' : 'text-white'}>
                          {profile.coagulation.inr}
                        </span>
                      </div>
                    )}
                    {profile.coagulation.pt && (
                      <div className="flex justify-between">
                        <span className="text-slate-400">PT</span>
                        <span className="text-white">{profile.coagulation.pt}</span>
                      </div>
                    )}
                    {profile.coagulation.reversal_needed && (
                      <div className="mt-2 p-2 bg-red-500/10 rounded text-red-400 text-sm">
                        ⚠️ Reversal may be needed
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-500">No coag panel</p>
                )}
              </div>
            </div>

            {/* Cardiac Clearance */}
            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                <Heart size={16} className="text-pink-400" />
                CARDIAC STATUS
              </h3>
              <div className="flex items-center justify-between">
                <div>
                  {profile.cardiac_clearance?.ejection_fraction && (
                    <p className="text-white">EF: {profile.cardiac_clearance.ejection_fraction}%</p>
                  )}
                  {profile.cardiac_clearance?.stress_test_result && (
                    <p className="text-slate-400 text-sm">
                      Stress Test: {profile.cardiac_clearance.stress_test_result}
                    </p>
                  )}
                </div>
                <RiskBadge level={profile.cardiac_risk} />
              </div>
            </div>

            {/* Critical Allergies */}
            {profile.critical_allergies.length > 0 && (
              <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/30">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-red-400 mb-3">
                  <AlertTriangle size={16} />
                  CRITICAL ALLERGIES
                </h3>
                <div className="space-y-2">
                  {profile.critical_allergies.map((allergy, i) => (
                    <div key={i} className="p-2 bg-red-500/10 rounded">
                      <span className="font-medium text-red-300">{allergy.allergen}</span>
                      {allergy.surgical_implication && (
                        <p className="text-sm text-red-400/80 mt-1">{allergy.surgical_implication}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* INTRA-OP VIEW */}
        {profile && activePhase === 'intraop' && (
          <div className="space-y-4">
            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                <FileText size={16} className="text-cyan-400" />
                VASCULAR SURGICAL HISTORY
              </h3>
              {profile.vascular_history.length > 0 ? (
                <div className="space-y-3">
                  {profile.vascular_history.map((proc, i) => (
                    <div key={i} className="p-3 bg-slate-800/50 rounded-lg border-l-4 border-cyan-500">
                      <p className="font-medium text-white">{proc.procedure}</p>
                      <div className="flex gap-4 mt-1 text-sm text-slate-400">
                        {proc.date && <span>{proc.date}</span>}
                        {proc.location && <span>📍 {proc.location}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500">No prior vascular interventions documented</p>
              )}
            </div>

            {/* Quick Reference */}
            <div className="grid grid-cols-2 gap-4">
              <div className={`p-4 rounded-lg border ${
                profile.contrast_caution 
                  ? 'bg-amber-500/10 border-amber-500/30' 
                  : 'bg-slate-900 border-slate-800'
              }`}>
                <p className="text-sm text-slate-400">Contrast Status</p>
                <p className={`text-lg font-semibold ${profile.contrast_caution ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {profile.contrast_caution ? 'Use Caution' : 'Standard Protocol'}
                </p>
              </div>
              <div className={`p-4 rounded-lg border ${
                profile.high_bleeding_risk 
                  ? 'bg-red-500/10 border-red-500/30' 
                  : 'bg-slate-900 border-slate-800'
              }`}>
                <p className="text-sm text-slate-400">Bleeding Risk</p>
                <p className={`text-lg font-semibold ${profile.high_bleeding_risk ? 'text-red-400' : 'text-emerald-400'}`}>
                  {profile.high_bleeding_risk ? 'Elevated' : 'Normal'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* POST-OP VIEW */}
        {profile && activePhase === 'postop' && (
          <div className="space-y-4">
            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                <Pill size={16} className="text-purple-400" />
                ANTICOAGULATION RESUMPTION PLAN
              </h3>
              {profile.antithrombotics.filter(m => ['vka', 'doac'].includes(m.category)).length > 0 ? (
                <div className="space-y-3">
                  {profile.antithrombotics
                    .filter(m => ['vka', 'doac'].includes(m.category))
                    .map((med, i) => (
                    <div key={i} className="p-3 bg-slate-800/50 rounded-lg">
                      <div className="flex justify-between items-center">
                        <span className="font-medium text-white">{med.name} {med.dose}</span>
                        <Clock size={14} className="text-slate-400" />
                      </div>
                      <p className="text-sm text-slate-400 mt-1">
                        Resume when hemostasis adequate (typically 24-48h post-op)
                      </p>
                      {med.reversal_agent && (
                        <p className="text-xs text-amber-400 mt-1">
                          Reversal if needed: {med.reversal_agent}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500">No anticoagulants to resume</p>
              )}
            </div>

            <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-300 mb-3">
                <Activity size={16} className="text-emerald-400" />
                MONITORING REQUIREMENTS
              </h3>
              <div className="space-y-2">
                {profile.contrast_caution && (
                  <div className="p-2 bg-amber-500/10 rounded text-amber-400 text-sm">
                    📊 Monitor renal function post-contrast (Cr at 24-48h)
                  </div>
                )}
                {profile.high_bleeding_risk && (
                  <div className="p-2 bg-red-500/10 rounded text-red-400 text-sm">
                    🩸 Enhanced bleeding surveillance
                  </div>
                )}
                <div className="p-2 bg-slate-800/50 rounded text-slate-300 text-sm">
                  ✓ Standard post-vascular monitoring protocol
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SurgicalDashboard;