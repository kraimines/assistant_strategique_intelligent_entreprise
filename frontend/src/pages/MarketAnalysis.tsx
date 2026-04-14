/**
 * MarketAnalysis.tsx — Intelligence de Marché page.
 *
 * Tabs:
 *   Vue Globale   — KPI cards, alerts feed, top analyses
 *   Knowledge Graph — force-directed KG viewer + hidden risks
 *   Prédictions GNN — impact bar chart, Talan gauge, systemic risk
 *   Actualités      — full LLM analyses feed with filters
 *   Prix & Marchés  — live price/volatility table
 */
import { useState, useCallback, lazy, Suspense, Component, type ReactNode, type ErrorInfo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TrendingUp, TrendingDown, ShieldAlert, Newspaper,
  GitBranch, Brain, BarChart2, Globe2, RefreshCw,
  AlertTriangle, Activity,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import PipelineStatusBar from '../components/MarketAnalysis/PipelineStatusBar';
import AlertsFeed from '../components/MarketAnalysis/AlertsFeed';
import NewsAnalysesFeed from '../components/MarketAnalysis/NewsAnalysesFeed';
import GNNPredictions from '../components/MarketAnalysis/GNNPredictions';
import PricesTicker from '../components/MarketAnalysis/PricesTicker';
import { marketAnalysisApi } from '../api/marketAnalysisApi';

// Lazy-load KGExplorer so a canvas/WebGL crash doesn't kill the whole page
const KGExplorer = lazy(() => import('../components/MarketAnalysis/KGExplorer'));

// ── Simple error boundary ─────────────────────────────────────────────────────
class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { error: Error | null }> {
  state = { error: null };
  static getDerivedStateFromError(e: Error) { return { error: e }; }
  componentDidCatch(e: Error, info: ErrorInfo) { console.error('MarketAnalysis crash:', e, info); }
  render() {
    if (this.state.error) {
      return this.props.fallback ?? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <AlertTriangle size={28} className="text-red-400" />
          <p className="text-white/50 text-sm">Composant indisponible</p>
          <p className="text-white/25 text-xs font-mono">{(this.state.error as Error).message}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Tab definition ─────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview',  icon: Globe2,      label: 'Vue Globale' },
  { id: 'kg',        icon: GitBranch,   label: 'Knowledge Graph' },
  { id: 'gnn',       icon: Brain,       label: 'Prédictions GNN' },
  { id: 'news',      icon: Newspaper,   label: 'Actualités' },
  { id: 'prices',    icon: BarChart2,   label: 'Prix & Marchés' },
] as const;

type TabId = typeof TABS[number]['id'];

// ── Overview KPI cards ─────────────────────────────────────────────────────────

function OverviewKPIs({
  alertsCount, criticalCount, analysesCount, avgImpact, kgNodes, kgRels,
}: {
  alertsCount: number;
  criticalCount: number;
  analysesCount: number;
  avgImpact: number;
  kgNodes: number;
  kgRels: number;
}) {
  const impactColor = avgImpact < -0.2 ? '#ef4444' : avgImpact > 0.2 ? '#10b981' : '#f59e0b';
  const kpis = [
    {
      icon: <ShieldAlert size={18} />,
      label: 'Alertes actives',
      value: String(alertsCount),
      sub: criticalCount > 0 ? `dont ${criticalCount} critique(s)` : 'Aucune critique',
      color: criticalCount > 0 ? '#ef4444' : '#10b981',
      glow: 'amber' as const,
    },
    {
      icon: <Newspaper size={18} />,
      label: 'Analyses LLM',
      value: String(analysesCount),
      sub: 'Dernières 24h',
      color: '#00d4ff',
      glow: 'cyan' as const,
    },
    {
      icon: avgImpact < 0 ? <TrendingDown size={18} /> : <TrendingUp size={18} />,
      label: 'Impact moyen Talan',
      value: `${avgImpact >= 0 ? '+' : ''}${avgImpact.toFixed(2)}`,
      sub: 'Score causal [-1, +1]',
      color: impactColor,
      glow: 'violet' as const,
    },
    {
      icon: <GitBranch size={18} />,
      label: 'Knowledge Graph',
      value: String(kgNodes),
      sub: `${kgRels} relations causales`,
      color: '#7c3aed',
      glow: 'violet' as const,
    },
  ];

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      {kpis.map((kpi, i) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.07 }}
        >
          <GlassCard hover glow={kpi.glow} className="p-5">
            <div className="flex items-start gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: `${kpi.color}14`, color: kpi.color }}
              >
                {kpi.icon}
              </div>
              <div className="min-w-0">
                <p className="text-white/35 text-[11px] leading-tight">{kpi.label}</p>
                <p className="text-2xl font-bold mt-1 leading-none" style={{ color: kpi.color }}>
                  {kpi.value}
                </p>
                <p className="text-white/30 text-[10px] mt-1.5">{kpi.sub}</p>
              </div>
            </div>
          </GlassCard>
        </motion.div>
      ))}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function MarketAnalysis() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [centerCompany, setCenterCompany] = useState('Talan');
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [runningGNN, setRunningGNN] = useState(false);
  const queryClient = useQueryClient();

  // ── Queries ────────────────────────────────────────────────────────────────

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['market', 'status'],
    queryFn: () => marketAnalysisApi.getStatus().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: alerts = [], isLoading: alertsLoading } = useQuery({
    queryKey: ['market', 'alerts'],
    queryFn: () => marketAnalysisApi.getAlerts(50).then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: analyses = [], isLoading: analysesLoading } = useQuery({
    queryKey: ['market', 'analyses'],
    queryFn: () => marketAnalysisApi.getAnalyses(24, 0, 50).then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: kgSnapshot, isLoading: kgLoading } = useQuery({
    queryKey: ['market', 'kg', 'snapshot', centerCompany],
    queryFn: () => marketAnalysisApi.getKGSnapshot(centerCompany, 2).then((r) => r.data),
    enabled: activeTab === 'kg' || activeTab === 'overview',
  });

  const { data: kgStats, isLoading: kgStatsLoading } = useQuery({
    queryKey: ['market', 'kg', 'stats'],
    queryFn: () => marketAnalysisApi.getKGStats().then((r) => r.data),
    refetchInterval: 120_000,
  });

  const { data: hiddenRisks = [], isLoading: hiddenLoading } = useQuery({
    queryKey: ['market', 'kg', 'hidden'],
    queryFn: () => marketAnalysisApi.getHiddenRisks(3).then((r) => r.data),
    enabled: activeTab === 'kg',
  });

  const { data: gnnResult, isLoading: gnnLoading, refetch: refetchGNN } = useQuery({
    queryKey: ['market', 'gnn'],
    queryFn: () => marketAnalysisApi.gnnPredict('on_demand').then((r) => r.data),
    enabled: activeTab === 'gnn',
    staleTime: 5 * 60_000,
  });

  const { data: prices, isLoading: pricesLoading, refetch: refetchPrices } = useQuery({
    queryKey: ['market', 'prices'],
    queryFn: () => marketAnalysisApi.getPrices().then((r) => r.data),
    enabled: activeTab === 'prices',
    staleTime: 60_000,
  });

  // ── Mutations ──────────────────────────────────────────────────────────────

  const handleRunPipeline = useCallback(async () => {
    setRunningPipeline(true);
    try {
      await marketAnalysisApi.runPipeline([], false);
      await queryClient.invalidateQueries({ queryKey: ['market'] });
    } catch (e) {
      console.error('Pipeline run failed', e);
    } finally {
      setRunningPipeline(false);
    }
  }, [queryClient]);

  const handleRunGNN = useCallback(async () => {
    setRunningGNN(true);
    try {
      await refetchGNN();
    } finally {
      setRunningGNN(false);
    }
  }, [refetchGNN]);

  // ── Computed ───────────────────────────────────────────────────────────────

  const criticalAlerts = alerts.filter((a) => a.level === 'critical' || a.level === 'high');
  const avgImpact = analyses.length
    ? analyses.reduce((s, a) => s + (a.talan_impact_score ?? 0), 0) / analyses.length
    : 0;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <AppShell title="Intelligence de Marché">
      <ErrorBoundary>
      <div className="p-6 space-y-5">

        {/* ── Page header ──────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.12)', color: '#00d4ff' }}>
                <Activity size={16} />
              </div>
              <h1 className="text-xl font-bold text-white/85">Intelligence de Marché</h1>
              {criticalAlerts.length > 0 && (
                <motion.span
                  animate={{ scale: [1, 1.05, 1] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs font-bold"
                  style={{ background: 'rgba(239,68,68,0.15)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.25)' }}
                >
                  <AlertTriangle size={11} />
                  {criticalAlerts.length} alerte(s) haute priorité
                </motion.span>
              )}
            </div>
            <p className="text-white/35 text-sm">
              Surveillance temps réel · Knowledge Graph causal · Prédictions GNN · Impact Talan
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['market'] })}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs transition-all"
              style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.45)' }}
            >
              <RefreshCw size={12} />
              Rafraîchir
            </button>
          </div>
        </div>

        {/* ── Pipeline status bar ───────────────────────────────────────────── */}
        <PipelineStatusBar
          status={status}
          loading={statusLoading}
          onRunNow={handleRunPipeline}
          running={runningPipeline}
        />

        {/* ── Tab navigation ────────────────────────────────────────────────── */}
        <div className="flex items-center gap-1 flex-wrap"
          style={{
            background: 'rgba(255,255,255,0.03)',
            borderRadius: '14px',
            padding: '4px',
            border: '1px solid rgba(255,255,255,0.07)',
            display: 'inline-flex',
          }}>
          {TABS.map(({ id, icon: Icon, label }) => {
            const isActive = activeTab === id;
            // Badge counts
            let badge: number | undefined;
            if (id === 'overview' && criticalAlerts.length > 0) badge = criticalAlerts.length;
            if (id === 'gnn' && gnnResult?.top_hidden_risks.length) badge = gnnResult.top_hidden_risks.length;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className="relative flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium transition-all duration-200"
                style={{
                  background: isActive ? 'rgba(0,212,255,0.10)' : 'transparent',
                  color: isActive ? '#00d4ff' : 'rgba(255,255,255,0.40)',
                  border: isActive ? '1px solid rgba(0,212,255,0.20)' : '1px solid transparent',
                }}
              >
                <Icon size={14} />
                <span className="hidden sm:inline">{label}</span>
                {badge !== undefined && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                    style={{ background: '#ef4444', color: 'white' }}>
                    {badge > 9 ? '9+' : badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Tab content ──────────────────────────────────────────────────── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >

            {/* ── Vue Globale ─────────────────────────────────────────────── */}
            {activeTab === 'overview' && (
              <div className="space-y-5">
                <OverviewKPIs
                  alertsCount={alerts.length}
                  criticalCount={criticalAlerts.length}
                  analysesCount={analyses.length}
                  avgImpact={avgImpact}
                  kgNodes={status?.kg_nodes ?? 0}
                  kgRels={status?.kg_relations ?? 0}
                />

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                  {/* Alerts */}
                  <GlassCard animate className="p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <ShieldAlert size={15} className="text-amber-400" />
                      <h3 className="text-sm font-semibold text-white/70">Alertes récentes</h3>
                      <span className="ml-auto text-[10px] text-white/25 font-mono">{alerts.length} total</span>
                    </div>
                    <AlertsFeed alerts={alerts.slice(0, 8)} loading={alertsLoading} />
                  </GlassCard>

                  {/* Top analyses */}
                  <GlassCard animate className="p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Newspaper size={15} className="text-cyan-400" />
                      <h3 className="text-sm font-semibold text-white/70">Dernières analyses</h3>
                      <span className="ml-auto text-[10px] text-white/25 font-mono">{analyses.length} analyses</span>
                    </div>
                    <NewsAnalysesFeed analyses={analyses.slice(0, 5)} loading={analysesLoading} />
                  </GlassCard>
                </div>

                {/* Mini KG snapshot */}
                {kgSnapshot && kgSnapshot.nodes.length > 0 && (
                  <GlassCard animate className="p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <GitBranch size={15} className="text-violet-400" />
                      <h3 className="text-sm font-semibold text-white/70">Knowledge Graph — Aperçu Talan</h3>
                      <button onClick={() => setActiveTab('kg')}
                        className="ml-auto text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors">
                        Voir complet →
                      </button>
                    </div>
                    <ErrorBoundary>
                      <Suspense fallback={<div className="h-64 bg-white/3 rounded-xl animate-pulse" />}>
                        <KGExplorer
                          snapshot={kgSnapshot}
                          stats={kgStats}
                          hiddenRisks={[]}
                          loading={kgLoading}
                          centerCompany={centerCompany}
                          onCompanyChange={setCenterCompany}
                        />
                      </Suspense>
                    </ErrorBoundary>
                  </GlassCard>
                )}
              </div>
            )}

            {/* ── Knowledge Graph ──────────────────────────────────────────── */}
            {activeTab === 'kg' && (
              <GlassCard animate className="p-5">
                <div className="flex items-center gap-2 mb-5">
                  <GitBranch size={16} className="text-violet-400" />
                  <h3 className="text-sm font-semibold text-white/75">Knowledge Graph Causal</h3>
                  <span className="text-[10px] text-white/30 ml-auto">
                    Nœuds: {kgStats?.total_nodes ?? '—'} · Relations: {kgStats?.total_relations ?? '—'}
                  </span>
                </div>
                <ErrorBoundary>
                  <Suspense fallback={<div className="h-96 bg-white/3 rounded-xl animate-pulse" />}>
                    <KGExplorer
                      snapshot={kgSnapshot}
                      stats={kgStats}
                      hiddenRisks={hiddenRisks}
                      loading={kgLoading || kgStatsLoading || hiddenLoading}
                      centerCompany={centerCompany}
                      onCompanyChange={(name) => { setCenterCompany(name); }}
                    />
                  </Suspense>
                </ErrorBoundary>
              </GlassCard>
            )}

            {/* ── GNN Predictions ──────────────────────────────────────────── */}
            {activeTab === 'gnn' && (
              <GlassCard animate className="p-5">
                <div className="flex items-center gap-2 mb-5">
                  <Brain size={16} className="text-violet-400" />
                  <h3 className="text-sm font-semibold text-white/75">Prédictions GNN — Impact Propagation</h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-md ml-2"
                    style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                    HeteroGATConv + Temporal Encoding
                  </span>
                </div>
                <GNNPredictions
                  result={gnnResult}
                  loading={gnnLoading}
                  onRunGNN={handleRunGNN}
                  running={runningGNN}
                />
              </GlassCard>
            )}

            {/* ── Actualités ────────────────────────────────────────────────── */}
            {activeTab === 'news' && (
              <GlassCard animate className="p-5">
                <div className="flex items-center gap-2 mb-5">
                  <Newspaper size={16} className="text-cyan-400" />
                  <h3 className="text-sm font-semibold text-white/75">Analyses LLM — Causalité & Impact</h3>
                  <span className="ml-auto text-[10px] text-white/30 font-mono">{analyses.length} analyses · 24h</span>
                </div>
                <NewsAnalysesFeed analyses={analyses} loading={analysesLoading} />
              </GlassCard>
            )}

            {/* ── Prix & Marchés ────────────────────────────────────────────── */}
            {activeTab === 'prices' && (
              <GlassCard animate className="p-5">
                <div className="flex items-center gap-2 mb-5">
                  <BarChart2 size={16} className="text-emerald-400" />
                  <h3 className="text-sm font-semibold text-white/75">Prix & Marchés — Snapshot Temps Réel</h3>
                </div>
                <PricesTicker
                  prices={prices}
                  loading={pricesLoading}
                  onRefresh={() => refetchPrices()}
                  refreshing={pricesLoading}
                />
              </GlassCard>
            )}

          </motion.div>
        </AnimatePresence>

      </div>
      </ErrorBoundary>
    </AppShell>
  );
}
