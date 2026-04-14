/**
 * CompetitiveIntel.tsx — Competitive intelligence visualization dashboard.
 *
 * Sections (top → bottom):
 *   1. Search bar — company tags + topic selector
 *   2. KPI strip  — threat level, news count, jobs count, last updated
 *   3. Row A       — ThreatRadar  |  NewsTimeline
 *   4. Row B       — JobSignalsChart (full width)
 *   5. Row C       — AnticipationPanel (full width) ← "what they will do"
 *   6. Row D       — StrategicRecommendations (full width)
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

// ── Constants ──────────────────────────────────────────────────────────────────

const TOPIC_OPTIONS = [
  'intelligence artificielle',
  'cloud computing',
  'cybersécurité',
  'digital transformation',
  'recrutement',
  'partenariats',
  'expansion marché',
  'fintech',
  'data & analytics',
];

const SUGGESTED_COMPANIES = [
  'Sopra Steria', 'Vermeg', 'Capgemini', 'Accenture', 'CGI',
  'Atos', 'Devoteam', 'Alten', 'Wavestone', 'IBM',
];

// ── KPI strip ──────────────────────────────────────────────────────────────────

function KpiStrip({ result }: { result: ScanResult }) {
  const { analysis } = result;
  const pct = Math.round(analysis.threat_level * 100);
  const threatColor =
    pct >= 75 ? '#ef4444' : pct >= 50 ? '#f97316' : pct >= 25 ? '#eab308' : '#22c55e';

  const kpis = [
    {
      icon: <ShieldAlert size={16} />,
      label: 'Niveau de menace',
      value: `${analysis.threat_label} (${pct}%)`,
      color: threatColor,
    },
    {
      icon: <Newspaper size={16} />,
      label: 'Actualités analysées',
      value: String(analysis.total_news),
      color: '#00d4ff',
    },
    {
      icon: <Briefcase size={16} />,
      label: 'Signaux recrutement',
      value: String(analysis.total_jobs),
      color: '#7c3aed',
    },
    {
      icon: <Clock size={16} />,
      label: 'Mouvements anticipés',
      value: String(analysis.anticipated_moves?.length ?? 0),
      color: '#f97316',
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
          <GlassCard className="p-4 flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: `${kpi.color}15`, color: kpi.color }}
            >
              {kpi.icon}
            </div>
            <div className="min-w-0">
              <p className="text-white/40 text-[10px] leading-tight">{kpi.label}</p>
              <p className="text-white font-semibold text-sm mt-0.5" style={{ color: kpi.color }}>
                {kpi.value}
              </p>
            </div>
          </GlassCard>
        </motion.div>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function CompetitiveIntel() {
  const [companies, setCompanies] = useState<string[]>(['Sopra Steria']);
  const [topic, setTopic] = useState('intelligence artificielle');
  const [inputValue, setInputValue] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);

  // ── Company tag management ────────────────────────────────────────────────

  const addCompany = (name: string) => {
    const t = name.trim();
    if (!t || companies.includes(t) || companies.length >= 5) return;
    setCompanies((p) => [...p, t]);
    setInputValue('');
    setShowSuggestions(false);
  };

  const removeCompany = (name: string) =>
    setCompanies((p) => p.filter((c) => c !== name));

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') addCompany(inputValue);
    if (e.key === 'Escape') setShowSuggestions(false);
  };

  // ── Scan ──────────────────────────────────────────────────────────────────

  const handleScan = async () => {
    if (!companies.length) return;
    setLoading(true);
    setError(null);
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

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <AppShell title="Veille Concurrentielle">
      <div className="p-6 space-y-6">

        {/* ── Controls ──────────────────────────────────────────────────────── */}
        <GlassCard animate className="p-5">
          <div className="flex flex-col gap-4">

            {/* Company tags */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-white/50 text-xs whitespace-nowrap flex-shrink-0">
                Concurrents :
              </span>

              <AnimatePresence>
                {companies.map((company) => (
                  <motion.span
                    key={company}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium
                      bg-cyber-cyan/10 border border-cyber-cyan/25 text-cyber-cyan"
                  >
                    {company}
                    <button
                      onClick={() => removeCompany(company)}
                      className="text-cyber-cyan/50 hover:text-cyber-cyan transition-colors"
                    >
                      <X size={11} />
                    </button>
                  </motion.span>
                ))}
              </AnimatePresence>

              {companies.length < 5 && (
                <div className="relative">
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                    bg-white/5 border border-white/10 text-white/60 text-xs">
                    <Plus size={11} />
                    <input
                      value={inputValue}
                      onChange={(e) => { setInputValue(e.target.value); setShowSuggestions(true); }}
                      onKeyDown={handleKeyDown}
                      onFocus={() => setShowSuggestions(true)}
                      onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                      placeholder="Ajouter…"
                      className="bg-transparent outline-none placeholder-white/25 w-32 text-white"
                    />
                  </div>
                  <AnimatePresence>
                    {showSuggestions && suggestions.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full left-0 mt-1 w-48 z-50 rounded-xl overflow-hidden shadow-2xl"
                        style={{ background: 'var(--bg-overlay-card)', border: '1px solid var(--border-subtle)' }}
                      >
                        {suggestions.slice(0, 6).map((s) => (
                          <button
                            key={s}
                            onMouseDown={() => addCompany(s)}
                            className="w-full text-left px-3 py-2 text-xs transition-colors"
                            style={{ color: 'var(--text-secondary)' }}
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
              <span className="text-white/50 text-xs whitespace-nowrap flex-shrink-0">
                Sujet stratégique :
              </span>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="theme-input rounded-lg px-3 py-1.5 text-xs focus:border-cyber-cyan/40 transition-colors cursor-pointer"
              >
                {TOPIC_OPTIONS.map((t) => (
                  <option key={t} value={t} style={{ background: 'var(--bg-card)' }}>{t}</option>
                ))}
              </select>

              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={handleClearCache}
                  title="Vider le cache"
                  className="p-1.5 rounded-lg text-white/25 hover:text-white/60
                    hover:bg-white/5 transition-all"
                >
                  <Trash2 size={14} />
                </button>
                <Button
                  onClick={handleScan}
                  disabled={loading || companies.length === 0}
                  icon={loading
                    ? <Loader2 size={14} className="animate-spin" />
                    : <Search size={14} />
                  }
                >
                  {loading ? 'Analyse…' : 'Analyser'}
                </Button>
              </div>
            </div>
          </div>
        </GlassCard>

        {/* ── Error ────────────────────────────────────────────────────────── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="flex items-center gap-3 p-4 rounded-xl bg-red-500/8
                border border-red-500/25 text-red-300 text-sm"
            >
              <AlertCircle size={16} className="flex-shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Empty state ──────────────────────────────────────────────────── */}
        {!result && !loading && !error && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-28 gap-5"
          >
            <div className="relative">
              <div className="w-20 h-20 rounded-2xl bg-cyber-cyan/8 border border-cyber-cyan/15
                flex items-center justify-center">
                <Search size={32} className="text-cyber-cyan/40" />
              </div>
              <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full
                bg-cyber-violet/30 border border-cyber-violet/40 flex items-center justify-center">
                <Clock size={10} className="text-cyber-violet" />
              </div>
            </div>
            <div className="text-center max-w-sm">
              <p className="text-white/50 text-sm font-medium mb-1">
                Analysez vos concurrents
              </p>
              <p className="text-white/25 text-xs leading-relaxed">
                Sélectionnez une ou plusieurs entreprises, choisissez un thème stratégique
                et lancez l'analyse pour visualiser leurs mouvements et anticiper leurs prochaines actions.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Loading ──────────────────────────────────────────────────────── */}
        {loading && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
              {[1,2,3,4].map(i => (
                <div key={i} className="h-16 rounded-xl bg-white/3 border border-white/6 animate-pulse" />
              ))}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {[1,2].map(i => (
                <div key={i} className="h-72 rounded-2xl bg-white/3 border border-white/6 animate-pulse" />
              ))}
            </div>
            <div className="h-56 rounded-2xl bg-white/3 border border-white/6 animate-pulse" />
            <div className="h-64 rounded-2xl bg-white/3 border border-white/6 animate-pulse" />
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        <AnimatePresence>
          {result && !loading && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="flex flex-col gap-6"
            >
              {/* Meta */}
              <div className="flex items-center gap-2 text-white/25 text-xs">
                <RefreshCw size={11} />
                <span>
                  Mis à jour le{' '}
                  {new Date(result.analysis.analyzed_at).toLocaleString('fr-FR', {
                    day: '2-digit', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                  {' · '}
                  {result.companies.join(', ')}
                  {' · '}
                  Thème : {result.topic}
                </span>
              </div>

              {/* KPI strip */}
              <KpiStrip result={result} />

              {/* Row A : Radar + News */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <ThreatRadar
                  scores={result.analysis.radar_scores}
                  threatLevel={result.analysis.threat_level}
                  threatLabel={result.analysis.threat_label}
                />
                <NewsTimeline articles={result.news} />
              </div>

              {/* Row B : Job signals */}
              {result.jobs && (
                <JobSignalsChart jobsData={result.jobs} />
              )}

              {/* Row C : Anticipation — WHAT THEY WILL DO */}
              <AnticipationPanel
                anticipatedMoves={result.analysis.anticipated_moves ?? []}
                hiringSignals={result.analysis.hiring_signals ?? []}
                companies={result.companies}
              />

              {/* Row D : Recommendations + Key moves */}
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
