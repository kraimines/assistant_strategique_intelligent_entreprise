/**
 * CompetitiveIntel.tsx — Competitive intelligence dashboard.
 * Cold light palette — dark readable text, larger font sizes.
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, X, Plus, RefreshCw, Trash2, AlertCircle, Loader2,
  Newspaper, Briefcase, Clock, ShieldAlert,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import ThreatRadar from '../components/CompetitiveIntel/ThreatRadar';
import NewsTimeline from '../components/CompetitiveIntel/NewsTimeline';
import JobSignalsChart from '../components/CompetitiveIntel/JobSignalsChart';
import AnticipationPanel from '../components/CompetitiveIntel/AnticipationPanel';
import StrategicRecommendations from '../components/CompetitiveIntel/StrategicRecommendations';
import GlassCard from '../components/ui/GlassCard';
import Button from '../components/ui/Button';

import { competitiveIntelApi } from '../api/competitiveIntelApi';
import type { ScanResult } from '../api/competitiveIntelApi';

const TOPIC_OPTIONS = [
  'intelligence artificielle', 'cloud computing', 'cybersécurité',
  'digital transformation', 'recrutement', 'partenariats',
  'expansion marché', 'fintech', 'data & analytics',
];

const SUGGESTED_COMPANIES = [
  'Sopra Steria', 'Vermeg', 'Capgemini', 'Accenture', 'CGI',
  'Atos', 'Devoteam', 'Alten', 'Wavestone', 'IBM',
];

/* ── KPI strip ───────────────────────────────────────────────────────────── */
function KpiStrip({ result }: { result: ScanResult }) {
  const { analysis } = result;
  const pct = Math.round(analysis.threat_level * 100);
  const threatColor =
    pct >= 75 ? '#DC2626' : pct >= 50 ? '#EA580C' : pct >= 25 ? '#D97706' : '#059669';

  const kpis = [
    {
      icon: <ShieldAlert size={18} />,
      label: 'Niveau de menace',
      value: `${analysis.threat_label} (${pct}%)`,
      color: threatColor,
      bg: `${threatColor}12`,
    },
    {
      icon: <Newspaper size={18} />,
      label: 'Actualités analysées',
      value: String(analysis.total_news),
      color: '#2563EB',
      bg: '#EFF6FF',
    },
    {
      icon: <Briefcase size={18} />,
      label: 'Signaux recrutement',
      value: String(analysis.total_jobs),
      color: '#7C3AED',
      bg: '#F5F3FF',
    },
    {
      icon: <Clock size={18} />,
      label: 'Mouvements anticipés',
      value: String(analysis.anticipated_moves?.length ?? 0),
      color: '#EA580C',
      bg: '#FFF7ED',
    },
  ];

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
      {kpis.map((kpi, i) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
        >
          <div
            className="p-4 rounded-[14px] flex items-center gap-3"
            style={{
              background: 'var(--bg-surface)',
              border:     '1px solid var(--border-subtle)',
              boxShadow:  'var(--shadow-card)',
            }}
          >
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: kpi.bg, color: kpi.color }}
            >
              {kpi.icon}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-faint)' }}>
                {kpi.label}
              </p>
              <p className="text-base font-bold mt-0.5" style={{ color: kpi.color }}>
                {kpi.value}
              </p>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

/* ── Main component ──────────────────────────────────────────────────────── */
export default function CompetitiveIntel() {
  const [companies,       setCompanies]       = useState<string[]>(['Sopra Steria']);
  const [topic,           setTopic]           = useState('intelligence artificielle');
  const [inputValue,      setInputValue]      = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading,         setLoading]         = useState(false);
  const [error,           setError]           = useState<string | null>(null);
  const [result,          setResult]          = useState<ScanResult | null>(null);

  const addCompany = (name: string) => {
    const t = name.trim();
    if (!t || companies.includes(t) || companies.length >= 5) return;
    setCompanies((p) => [...p, t]);
    setInputValue('');
    setShowSuggestions(false);
  };
  const removeCompany = (name: string) => setCompanies((p) => p.filter((c) => c !== name));
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter')  addCompany(inputValue);
    if (e.key === 'Escape') setShowSuggestions(false);
  };

  const handleScan = async () => {
    if (!companies.length) return;
    setLoading(true); setError(null);
    try {
      const resp = await competitiveIntelApi.scan(companies, topic, 8);
      setResult(resp.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Erreur lors du scan. Vérifiez votre connexion.');
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = async () => {
    try { await competitiveIntelApi.clearCache(); } catch { /* silent */ }
  };

  const suggestions = SUGGESTED_COMPANIES.filter(
    (c) => !companies.includes(c) && c.toLowerCase().includes(inputValue.toLowerCase()),
  );

  return (
    <AppShell title="Veille Concurrentielle">
      <div
        className="p-6 space-y-6"
        style={{
          background: 'linear-gradient(180deg, #F8FAFC 0%, #F8FBFF 45%, #FDFDFF 100%)',
        }}
      >
        <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -top-24 -right-20 h-72 w-72 rounded-full bg-sky-100/60 blur-3xl" />
          <div className="absolute top-40 -left-28 h-80 w-80 rounded-full bg-violet-100/55 blur-3xl" />
          <div className="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-emerald-100/40 blur-3xl" />
        </div>

        {/* ── Controls card ────────────────────────────────────────────── */}
        <GlassCard animate className="p-6">
          <div className="flex flex-col gap-4">

            {/* Company tags */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
                Concurrents :
              </span>

              <AnimatePresence>
                {companies.map((company) => (
                  <motion.span
                    key={company}
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold"
                    style={{
                      background:  '#EFF6FF',
                      border:      '1px solid #BFDBFE',
                      color:       '#1D4ED8',
                    }}
                  >
                    {company}
                    <button
                      onClick={() => removeCompany(company)}
                      className="opacity-60 hover:opacity-100 transition-opacity"
                    >
                      <X size={12} />
                    </button>
                  </motion.span>
                ))}
              </AnimatePresence>

              {companies.length < 5 && (
                <div className="relative">
                  <div
                    className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm"
                    style={{
                      background: 'var(--bg-base)',
                      border:     '1px solid var(--border-subtle)',
                      color:      'var(--text-muted)',
                    }}
                  >
                    <Plus size={13} />
                    <input
                      value={inputValue}
                      onChange={(e) => { setInputValue(e.target.value); setShowSuggestions(true); }}
                      onKeyDown={handleKeyDown}
                      onFocus={() => setShowSuggestions(true)}
                      onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                      placeholder="Ajouter…"
                      className="bg-transparent outline-none w-28"
                      style={{ color: 'var(--text-primary)' }}
                    />
                  </div>

                  <AnimatePresence>
                    {showSuggestions && suggestions.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full left-0 mt-1.5 w-48 z-50 rounded-xl overflow-hidden"
                        style={{
                          background: 'var(--bg-surface)',
                          border:     '1px solid var(--border-subtle)',
                          boxShadow:  'var(--shadow-card-md)',
                        }}
                      >
                        {suggestions.slice(0, 6).map((s) => (
                          <button
                            key={s}
                            onMouseDown={() => addCompany(s)}
                            className="w-full text-left px-3 py-2.5 text-sm font-medium transition-colors"
                            style={{ color: 'var(--text-secondary)' }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                            }}
                          >
                            {s}
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>

            {/* Topic + actions */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-base font-semibold flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
                Sujet stratégique :
              </span>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="theme-input rounded-xl px-3 py-2.5 text-base cursor-pointer"
                style={{ color: 'var(--text-primary)' }}
              >
                {TOPIC_OPTIONS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>

              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={handleClearCache}
                  title="Vider le cache"
                  className="p-2 rounded-xl transition-all"
                  style={{ color: 'var(--text-faint)' }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-faint)';
                  }}
                >
                  <Trash2 size={15} />
                </button>
                <Button
                  onClick={handleScan}
                  disabled={loading || companies.length === 0}
                  icon={loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
                >
                  {loading ? 'Analyse en cours…' : 'Analyser'}
                </Button>
              </div>
            </div>
          </div>
        </GlassCard>

        {/* ── Error ───────────────────────────────────────────────────── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="flex items-center gap-3 p-4 rounded-xl text-sm font-medium"
              style={{
                background:  'var(--danger-subtle)',
                border:      '1px solid rgba(239,68,68,0.25)',
                color:       'var(--danger)',
              }}
            >
              <AlertCircle size={16} className="flex-shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Empty state ──────────────────────────────────────────────── */}
        {!result && !loading && !error && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-28 gap-5"
          >
            <div className="relative">
              <div
                className="w-20 h-20 rounded-2xl flex items-center justify-center"
                style={{
                  background: '#EFF6FF',
                  border:     '1px solid #BFDBFE',
                }}
              >
                <Search size={32} style={{ color: '#93C5FD' }} />
              </div>
              <div
                className="absolute -top-1.5 -right-1.5 w-6 h-6 rounded-full flex items-center justify-center"
                style={{ background: '#F5F3FF', border: '1px solid #DDD6FE' }}
              >
                <Clock size={12} style={{ color: '#7C3AED' }} />
              </div>
            </div>
            <div className="text-center max-w-sm">
              <p className="text-base font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                Analysez vos concurrents
              </p>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                Sélectionnez une ou plusieurs entreprises, choisissez un thème stratégique
                et lancez l'analyse pour visualiser leurs mouvements.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Skeleton loading ─────────────────────────────────────────── */}
        {loading && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
              {[1,2,3,4].map(i => (
                <div key={i} className="h-20 rounded-2xl animate-pulse" style={{ background: 'var(--border-subtle)' }} />
              ))}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {[1,2].map(i => (
                <div key={i} className="h-72 rounded-2xl animate-pulse" style={{ background: 'var(--border-subtle)' }} />
              ))}
            </div>
            <div className="h-56 rounded-2xl animate-pulse" style={{ background: 'var(--border-subtle)' }} />
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────── */}
        <AnimatePresence>
          {result && !loading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="flex flex-col gap-6"
            >
              {/* Meta info */}
              <div
                className="flex items-center gap-2 text-xs font-medium"
                style={{ color: 'var(--text-faint)' }}
              >
                <RefreshCw size={12} />
                <span>
                  Mis à jour le{' '}
                  {new Date(result.analysis.analyzed_at).toLocaleString('fr-FR', {
                    day: '2-digit', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                  {' · '}{result.companies.join(', ')}
                  {' · '}Thème : {result.topic}
                </span>
              </div>

              <KpiStrip result={result} />

              {/* Row A: Radar + News */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <ThreatRadar
                  scores={result.analysis.radar_scores}
                  threatLevel={result.analysis.threat_level}
                  threatLabel={result.analysis.threat_label}
                />
                <NewsTimeline articles={result.news} />
              </div>

              {/* Row B: Job signals */}
              {result.jobs && <JobSignalsChart jobsData={result.jobs} />}

              {/* Row C: Anticipation */}
              <AnticipationPanel
                anticipatedMoves={result.analysis.anticipated_moves ?? []}
                hiringSignals={result.analysis.hiring_signals ?? []}
                companies={result.companies}
              />

              {/* Row D: Recommendations */}
              <StrategicRecommendations
                recommendations={result.analysis.recommended_actions}
                keyMoves={result.analysis.key_moves}
                summary={result.analysis.summary}
              />
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </AppShell>
  );
}
