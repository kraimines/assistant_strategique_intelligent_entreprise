/**
 * MarketAnalysis.tsx — Intelligence de Marché
 *
 * Structure Option B — 3 groupes métier :
 *   Situation actuelle   → Tableau de bord · Veille · Marchés
 *   Analyse des risques  → Carte causale · Signaux IA
 *   Actions              → Plan d'action
 *
 * UX :
 *  - Navigation groupée avec couleurs par domaine
 *  - PipelineFlowBanner : flux visuel Veille → IA → KG → GNN → Actions
 *  - TabContextBar : sous-titre + lien vers l'étape suivante
 *  - Analyses LLM fusionnées dans l'onglet Veille (sous-toggle)
 *  - KG par défaut en vue 2D lisible
 */
import {
  useState, useCallback, lazy, Suspense,
  Component, type ReactNode, type ErrorInfo,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, TrendingDown, ShieldAlert, Newspaper,
  GitBranch, Brain, BarChart2, Globe2, RefreshCw,
  MessageSquare, AlertTriangle, Activity, Lightbulb,
  FlaskConical, ArrowRight, ChevronRight, Zap,
  CheckCircle2, Circle, FileDown, Loader2,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import PipelineStatusBar from '../components/MarketAnalysis/PipelineStatusBar';
import AlertsFeed from '../components/MarketAnalysis/AlertsFeed';
import EnrichedNewsFeed from '../components/MarketAnalysis/EnrichedNewsFeed';
import NewsAnalysesFeed from '../components/MarketAnalysis/NewsAnalysesFeed';
import KGReadableGraph from '../components/MarketAnalysis/KGReadableGraph';
import FullGraphViewer from '../components/MarketAnalysis/FullGraphViewer';
import GNNPredictions from '../components/MarketAnalysis/GNNPredictions';
import PricesTicker from '../components/MarketAnalysis/PricesTicker';
import StrategicRecommendations from '../components/MarketAnalysis/StrategicRecommendations';
import { marketAnalysisApi } from '../api/marketAnalysisApi';
import type { RecommendationResult } from '../api/marketAnalysisApi';

const KGExplorer = lazy(() => import('../components/MarketAnalysis/KGExplorer'));

// ── Error boundary ─────────────────────────────────────────────────────────────
class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { error: Error | null }
> {
  state = { error: null };
  static getDerivedStateFromError(e: Error) { return { error: e }; }
  componentDidCatch(e: Error, info: ErrorInfo) { console.error('MarketAnalysis crash:', e, info); }
  render() {
    if (this.state.error)
      return this.props.fallback ?? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <AlertTriangle size={28} className="text-red-400" />
          <p className="text-[var(--text-secondary)] text-sm font-medium">Composant indisponible</p>
          <p className="text-[var(--text-faint)] text-xs font-mono">
            {(this.state.error as Error).message}
          </p>
        </div>
      );
    return this.props.children;
  }
}

// ── Navigation groupée ─────────────────────────────────────────────────────────

const TAB_GROUPS = [
  {
    id: 'situation',
    label: 'Situation actuelle',
    color: '#0EA5E9',
    tabs: [
      {
        id: 'overview' as const,
        icon: Globe2,
        label: 'Tableau de bord',
        desc: 'Alertes prioritaires, KPI et vue d\'ensemble en temps réel',
      },
      {
        id: 'enriched' as const,
        icon: Newspaper,
        label: 'Veille',
        desc: 'Actualités filtrées par impact et analysées par l\'IA',
      },
      {
        id: 'prices' as const,
        icon: BarChart2,
        label: 'Marchés',
        desc: 'Prix, volatilité et signaux financiers des concurrents',
      },
    ],
  },
  {
    id: 'risks',
    label: 'Analyse des risques',
    color: '#8B5CF6',
    tabs: [
      {
        id: 'kg' as const,
        icon: GitBranch,
        label: 'Carte causale',
        desc: 'Relations entre acteurs du marché et chemins de propagation des risques',
      },
      {
        id: 'gnn' as const,
        icon: Brain,
        label: 'Signaux IA',
        desc: 'Prédictions TGAT sur l\'impact des événements jusqu\'à Talan',
      },
    ],
  },
  {
    id: 'actions',
    label: 'Actions',
    color: '#F59E0B',
    tabs: [
      {
        id: 'recommend' as const,
        icon: Lightbulb,
        label: 'Plan d\'action',
        desc: 'Recommandations stratégiques générées par l\'IA et prioritisées',
      },
    ],
  },
] as const;

type TabId = 'overview' | 'enriched' | 'prices' | 'kg' | 'gnn' | 'recommend';

const TAB_CONTEXT: Record<TabId, { desc: string; next: { label: string; tab: TabId } | null }> = {
  overview: {
    desc: 'Vue synthétique de la situation — alertes critiques, KPI et flux marché en direct.',
    next: { label: 'Explorer la Veille', tab: 'enriched' },
  },
  enriched: {
    desc: 'Actualités classées par score d\'impact (1–10) et analysées par LLM : entités extraites, relations causales, pertinence Talan.',
    next: { label: 'Voir la Carte causale', tab: 'kg' },
  },
  prices: {
    desc: 'Snapshots prix/volatilité en temps réel pour Talan, concurrents cotés et indices de référence.',
    next: { label: 'Voir les Signaux IA', tab: 'gnn' },
  },
  kg: {
    desc: 'Knowledge Graph causal construit automatiquement à partir des analyses LLM. Chaque lien = relation de causalité extraite d\'un article.',
    next: { label: 'Voir les Signaux IA', tab: 'gnn' },
  },
  gnn: {
    desc: 'Le modèle TGAT (Temporal Graph Attention Network) calcule la propagation d\'impact de chaque événement jusqu\'à Talan via le graphe causal.',
    next: { label: 'Voir le Plan d\'action', tab: 'recommend' },
  },
  recommend: {
    desc: 'Recommandations stratégiques générées par LLM à partir des prédictions GNN + prévisions LSTM, triées par urgence et domaine.',
    next: null,
  },
};

// ── Pipeline Flow Banner ───────────────────────────────────────────────────────

interface FlowCounts {
  news: number;
  analyses: number;
  kgNodes: number;
  gnnPreds: number;
  recs: number;
}

function PipelineFlowBanner({
  counts,
  onNavigate,
}: {
  counts: FlowCounts;
  onNavigate: (tab: TabId) => void;
}) {
  const steps: {
    icon: typeof Newspaper;
    label: string;
    sub: string;
    tab: TabId | null;
    color: string;
    done: boolean;
  }[] = [
    {
      icon: Newspaper,
      label: 'Collecte',
      sub: `${counts.news} articles`,
      tab: 'enriched',
      color: '#0EA5E9',
      done: counts.news > 0,
    },
    {
      icon: FlaskConical,
      label: 'Analyse IA',
      sub: `${counts.analyses} analysés`,
      tab: 'enriched',
      color: '#6366F1',
      done: counts.analyses > 0,
    },
    {
      icon: GitBranch,
      label: 'Carte causale',
      sub: `${counts.kgNodes} entités`,
      tab: 'kg',
      color: '#8B5CF6',
      done: counts.kgNodes > 0,
    },
    {
      icon: Brain,
      label: 'Signaux IA',
      sub: counts.gnnPreds > 0 ? `${counts.gnnPreds} prédictions` : 'À lancer',
      tab: 'gnn',
      color: '#EC4899',
      done: counts.gnnPreds > 0,
    },
    {
      icon: Lightbulb,
      label: 'Plan d\'action',
      sub: counts.recs > 0 ? `${counts.recs} actions` : 'À générer',
      tab: 'recommend',
      color: '#F59E0B',
      done: counts.recs > 0,
    },
  ];

  return (
    <div
      className="rounded-2xl p-4"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-faint)] mb-3">
        Flux d'intelligence — de la veille à la décision
      </p>
      <div className="flex items-center gap-1 flex-wrap">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-1">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => step.tab && onNavigate(step.tab)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all"
              style={{
                background: step.done ? `${step.color}10` : 'var(--bg-base)',
                border: `1px solid ${step.done ? step.color + '30' : 'var(--border-subtle)'}`,
                cursor: step.tab ? 'pointer' : 'default',
              }}
            >
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: step.done ? `${step.color}18` : 'var(--bg-base)', color: step.done ? step.color : 'var(--text-faint)' }}
              >
                <step.icon size={14} />
              </div>
              <div className="text-left">
                <div className="flex items-center gap-1">
                  <p className="text-[11px] font-bold" style={{ color: step.done ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                    {step.label}
                  </p>
                  {step.done
                    ? <CheckCircle2 size={10} style={{ color: step.color }} />
                    : <Circle size={10} className="text-[var(--text-faint)]" />}
                </div>
                <p className="text-[10px]" style={{ color: step.done ? step.color : 'var(--text-faint)' }}>
                  {step.sub}
                </p>
              </div>
            </motion.button>
            {i < steps.length - 1 && (
              <ArrowRight size={12} className="text-[var(--text-faint)] flex-shrink-0" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tab Context Bar ────────────────────────────────────────────────────────────

function TabContextBar({
  tab,
  onNavigate,
}: {
  tab: TabId;
  onNavigate: (tab: TabId) => void;
}) {
  const ctx = TAB_CONTEXT[tab];
  const group = TAB_GROUPS.find((g) => g.tabs.some((t) => t.id === tab));
  const groupColor = group?.color ?? 'var(--primary)';

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 rounded-xl flex-wrap"
      style={{
        background: `${groupColor}08`,
        border: `1px solid ${groupColor}20`,
      }}
    >
      <p className="text-xs text-[var(--text-secondary)] flex-1 min-w-0">{ctx.desc}</p>
      {ctx.next && (
        <button
          onClick={() => onNavigate(ctx.next!.tab)}
          className="flex items-center gap-1 text-[11px] font-semibold whitespace-nowrap transition-all hover:gap-1.5"
          style={{ color: groupColor }}
        >
          {ctx.next.label}
          <ChevronRight size={12} />
        </button>
      )}
    </div>
  );
}

// ── Overview KPIs ──────────────────────────────────────────────────────────────

function OverviewKPIs({
  alertsCount,
  criticalCount,
  newsCount,
  avgImpact,
  kgNodes,
  kgRels,
}: {
  alertsCount: number;
  criticalCount: number;
  newsCount: number;
  avgImpact: number;
  kgNodes: number;
  kgRels: number;
}) {
  const impactColor =
    avgImpact < -0.2 ? '#ef4444' : avgImpact > 0.2 ? '#10b981' : '#f59e0b';
  const kpis = [
    {
      icon: <ShieldAlert size={18} />,
      label: 'Alertes actives',
      value: String(alertsCount),
      sub: criticalCount > 0 ? `dont ${criticalCount} critique(s)` : 'Aucune critique',
      color: criticalCount > 0 ? '#ef4444' : '#10b981',
    },
    {
      icon: <Newspaper size={18} />,
      label: 'Articles collectés',
      value: String(newsCount),
      sub: 'Dernières 24h · score ≥ 5',
      color: '#00d4ff',
    },
    {
      icon:
        avgImpact < 0 ? <TrendingDown size={18} /> : <TrendingUp size={18} />,
      label: 'Signal d\'impact Talan',
      value: `${avgImpact >= 0 ? '+' : ''}${avgImpact.toFixed(2)}`,
      sub: 'Score causal moyen [-1, +1]',
      color: impactColor,
    },
    {
      icon: <GitBranch size={18} />,
      label: 'Carte causale',
      value: String(kgNodes),
      sub: `${kgRels} liens de causalité`,
      color: '#7c3aed',
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
          <GlassCard hover className="p-5">
            <div className="flex items-start gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: `${kpi.color}14`, color: kpi.color }}
              >
                {kpi.icon}
              </div>
              <div className="min-w-0">
                <p className="text-[var(--text-muted)] text-sm leading-tight">{kpi.label}</p>
                <p className="text-2xl font-bold mt-1 leading-none" style={{ color: kpi.color }}>
                  {kpi.value}
                </p>
                <p className="text-[var(--text-faint)] text-xs mt-1.5">{kpi.sub}</p>
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
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [centerCompany, setCenterCompany] = useState('Talan');
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [runningGNN, setRunningGNN] = useState(false);
  const [generatingRec, setGeneratingRec] = useState(false);
  const [recResult, setRecResult] = useState<RecommendationResult | null>(null);
  const [kgView, setKgView] = useState<'2d' | '3d' | 'full'>('2d');
  const [veilleSubTab, setVeilleSubTab] = useState<'news' | 'analyses'>('news');
  const [exportingBrief, setExportingBrief] = useState(false);
  const [exportError,    setExportError]    = useState<string | null>(null);
  const queryClient = useQueryClient();

  const handleExportBrief = useCallback(async () => {
    if (exportingBrief) return;
    setExportingBrief(true);
    setExportError(null);
    try {
      const resp = await marketAnalysisApi.exportBrief({
        period_days: 7,
        max_paths:   5,
        max_alerts:  5,
      });
      // axios returns the Blob in resp.data
      const blob = resp.data instanceof Blob ? resp.data : new Blob([resp.data], { type: 'application/pdf' });
      const url  = URL.createObjectURL(blob);
      const ts   = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `talan-brief-comex-${ts}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (err: any) {
      let msg = "Échec de l'export";
      // When responseType:'blob', axios wraps error body as a Blob — read it back
      const blobData = err?.response?.data;
      if (blobData instanceof Blob) {
        try {
          const text = await blobData.text();
          const json = JSON.parse(text);
          msg = json?.detail ?? msg;
        } catch {
          msg = err?.message ?? msg;
        }
      } else {
        msg = err?.response?.data?.detail ?? err?.message ?? msg;
      }
      setExportError(msg);
    } finally {
      setExportingBrief(false);
    }
  }, [exportingBrief]);

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

  const { data: analyses = [] } = useQuery({
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

  const {
    data: kgFull,
    isLoading: kgFullLoading,
    refetch: refetchKGFull,
    isFetching: kgFullFetching,
  } = useQuery({
    queryKey: ['market', 'kg', 'full'],
    queryFn: () => (marketAnalysisApi as any).getKGFull(1200).then((r: any) => r.data),
    enabled: activeTab === 'kg' && kgView === 'full',
    staleTime: 5 * 60_000,
  });

  const { data: prices, isLoading: pricesLoading, refetch: refetchPrices } = useQuery({
    queryKey: ['market', 'prices'],
    queryFn: () => marketAnalysisApi.getPrices().then((r) => r.data),
    enabled: activeTab === 'prices',
    staleTime: 60_000,
  });

  const [enrichedLive, setEnrichedLive] = useState(false);
  const {
    data: enrichedNews = [],
    isLoading: enrichedLoading,
    refetch: refetchEnriched,
    isFetching: enrichedFetching,
  } = useQuery({
    queryKey: ['market', 'enriched', enrichedLive],
    queryFn: () =>
      marketAnalysisApi.getEnrichedNews(5, false, enrichedLive).then((r) => r.data),
    enabled: activeTab === 'enriched' || activeTab === 'overview',
    staleTime: 5 * 60_000,
  });

  const { data: forecastResult, isLoading: forecastLoading } = useQuery({
    queryKey: ['market', 'forecast'],
    queryFn: () => marketAnalysisApi.getForecast().then((r) => r.data),
    enabled: activeTab === 'recommend',
    staleTime: 5 * 60_000,
  });

  // ── Handlers ───────────────────────────────────────────────────────────────

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
    try { await refetchGNN(); }
    finally { setRunningGNN(false); }
  }, [refetchGNN]);

  const handleGenerateRec = useCallback(async () => {
    setGeneratingRec(true);
    try {
      const res = await marketAnalysisApi.getRecommendations();
      setRecResult(res.data);
    } catch (e) {
      console.error('Recommendations failed', e);
    } finally {
      setGeneratingRec(false);
    }
  }, []);

  // ── Computed ───────────────────────────────────────────────────────────────

  const criticalAlerts = alerts.filter(
    (a) => a.level === 'critical' || a.level === 'high',
  );
  const avgImpact = analyses.length
    ? analyses.reduce((s, a) => s + (a.talan_impact_score ?? 0), 0) / analyses.length
    : 0;


  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <AppShell title="Intelligence de Marché">
      <ErrorBoundary>
        <div
          className="p-6 space-y-4"
          style={{
            background: 'linear-gradient(180deg, #F8FAFC 0%, #F8FBFF 45%, #FDFDFF 100%)',
          }}
        >
          {/* Background blobs */}
          <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
            <div className="absolute -top-28 -right-24 h-80 w-80 rounded-full bg-sky-100/60 blur-3xl" />
            <div className="absolute top-56 -left-24 h-72 w-72 rounded-full bg-violet-100/45 blur-3xl" />
            <div className="absolute bottom-0 right-1/3 h-64 w-64 rounded-full bg-emerald-100/35 blur-3xl" />
          </div>

          {/* ── Page header ──────────────────────────────────────────────────── */}
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <div
                  className="w-8 h-8 rounded-xl flex items-center justify-center"
                  style={{ background: 'var(--primary-subtle)', color: 'var(--primary)' }}
                >
                  <Activity size={16} />
                </div>
                <h1
                  className="text-2xl font-bold"
                  style={{ color: 'var(--text-primary)' }}
                >
                  Intelligence de Marché
                </h1>
                {criticalAlerts.length > 0 && (
                  <motion.span
                    animate={{ scale: [1, 1.05, 1] }}
                    transition={{ repeat: Infinity, duration: 2 }}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold"
                    style={{
                      background: '#FEF2F2',
                      color: '#DC2626',
                      border: '1px solid rgba(220,38,38,0.2)',
                    }}
                  >
                    <AlertTriangle size={11} />
                    {criticalAlerts.length} alerte{criticalAlerts.length > 1 ? 's' : ''} prioritaire{criticalAlerts.length > 1 ? 's' : ''}
                  </motion.span>
                )}
              </div>
              <p className="text-[var(--text-muted)] text-sm">
                Veille automatique · Analyse causale IA · Prédictions GNN · Recommandations stratégiques
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() =>
                  navigate(
                    '/chat?context=Analyse%20de%20march%C3%A9%20Talan%20%3A%20croise%20les%20alertes%2C%20le%20Knowledge%20Graph%20et%20les%20pr%C3%A9dictions%20GNN',
                  )
                }
                className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm transition-all"
                style={{
                  background: 'var(--primary-subtle)',
                  color: 'var(--primary-dark)',
                  border: '1px solid var(--primary-muted)',
                }}
              >
                <MessageSquare size={12} />
                Ouvrir l'assistant
              </button>
              <button
                onClick={() =>
                  queryClient.invalidateQueries({ queryKey: ['market'] })
                }
                className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm transition-all"
                style={{
                  background: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <RefreshCw size={12} />
                Rafraîchir
              </button>
              <button
                onClick={handleExportBrief}
                disabled={exportingBrief}
                title="Générer un brief PDF prêt à partager avec le COMEX"
                className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-semibold transition-all disabled:opacity-60"
                style={{
                  background: '#0B1F4A',
                  color: 'white',
                  border: '1px solid #0B1F4A',
                }}
              >
                {exportingBrief
                  ? <Loader2 size={12} className="animate-spin" />
                  : <FileDown size={12} />}
                {exportingBrief ? 'Génération…' : 'Brief Comex (PDF)'}
              </button>
            </div>
          </div>
          {exportError && (
            <div
              className="px-3 py-1.5 rounded-md text-xs font-medium"
              style={{ background: '#FEE2E2', color: '#B91C1C',
                       border: '1px solid #FECACA', alignSelf: 'flex-end' }}
            >
              ⚠ Export brief : {exportError}
            </div>
          )}

          {/* ── Pipeline status bar ───────────────────────────────────────────── */}
          <PipelineStatusBar
            status={status}
            loading={statusLoading}
            onRunNow={handleRunPipeline}
            running={runningPipeline}
          />

          {/* ── Navigation groupée ────────────────────────────────────────────── */}
          <div
            className="rounded-2xl p-3"
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            <div className="flex items-stretch gap-3 flex-wrap">
              {TAB_GROUPS.map((group, gi) => (
                <div key={group.id} className="flex items-stretch gap-2">
                  {/* Separator between groups */}
                  {gi > 0 && (
                    <div
                      className="w-px self-stretch mx-1"
                      style={{ background: 'var(--border-subtle)' }}
                    />
                  )}
                  <div className="flex flex-col gap-1.5">
                    {/* Group label */}
                    <p
                      className="text-[9px] font-black uppercase tracking-widest px-1"
                      style={{ color: group.color }}
                    >
                      {group.label}
                    </p>
                    {/* Tabs in group */}
                    <div className="flex items-center gap-1">
                      {group.tabs.map(({ id, icon: Icon, label }) => {
                        const isActive = activeTab === id;
                        let badge: number | undefined;
                        if (id === 'overview' && criticalAlerts.length > 0)
                          badge = criticalAlerts.length;
                        if (id === 'gnn' && (gnnResult?.top_hidden_risks.length ?? 0) > 0)
                          badge = gnnResult!.top_hidden_risks.length;
                        if (id === 'enriched' && enrichedNews.length > 0)
                          badge = enrichedNews.length;
                        return (
                          <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            className="relative flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-200"
                            style={{
                              background: isActive
                                ? `${group.color}15`
                                : 'transparent',
                              color: isActive ? group.color : 'var(--text-muted)',
                              border: `1px solid ${isActive ? group.color + '35' : 'transparent'}`,
                            }}
                          >
                            <Icon size={13} />
                            <span className="hidden sm:inline">{label}</span>
                            {badge !== undefined && (
                              <span
                                className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
                                style={{ background: '#ef4444', color: 'white' }}
                              >
                                {badge > 9 ? '9+' : badge}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ))}

              {/* Quick action: lancer pipeline */}
              <div className="ml-auto flex items-end pb-0.5">
                <button
                  onClick={handleRunPipeline}
                  disabled={runningPipeline}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all"
                  style={{
                    background: runningPipeline ? 'var(--border-subtle)' : '#F0FDF4',
                    color: runningPipeline ? 'var(--text-faint)' : '#059669',
                    border: '1px solid #BBF7D0',
                  }}
                >
                  {runningPipeline ? (
                    <>
                      <span className="w-3 h-3 border-2 border-emerald-300 border-t-emerald-600 rounded-full animate-spin" />
                      En cours…
                    </>
                  ) : (
                    <>
                      <Zap size={11} />
                      Lancer l'analyse
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* ── Context bar ───────────────────────────────────────────────────── */}
          <TabContextBar tab={activeTab} onNavigate={setActiveTab} />

          {/* ── Tab content ──────────────────────────────────────────────────── */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
              className="space-y-5"
            >

              {/* ── TABLEAU DE BORD ───────────────────────────────────────────── */}
              {activeTab === 'overview' && (
                <>
                  {/* Pipeline flow banner */}
                  <PipelineFlowBanner
                    counts={{
                      news: enrichedNews.length,
                      analyses: analyses.length,
                      kgNodes: kgStats?.total_nodes ?? 0,
                      gnnPreds: gnnResult?.predictions.length ?? 0,
                      recs: recResult?.recommendations.length ?? 0,
                    }}
                    onNavigate={setActiveTab}
                  />

                  {/* KPIs */}
                  <OverviewKPIs
                    alertsCount={alerts.length}
                    criticalCount={criticalAlerts.length}
                    newsCount={enrichedNews.length}
                    avgImpact={avgImpact}
                    kgNodes={kgStats?.total_nodes ?? 0}
                    kgRels={kgStats?.total_relations ?? 0}
                  />

                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                    {/* Alertes */}
                    <GlassCard animate className="p-5">
                      <div className="flex items-center gap-2 mb-4">
                        <ShieldAlert size={15} className="text-amber-400" />
                        <h3
                          className="text-base font-semibold"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          Alertes prioritaires
                        </h3>
                        <span className="ml-auto text-xs text-[var(--text-faint)] font-mono">
                          {alerts.length} total
                        </span>
                      </div>
                      <AlertsFeed alerts={alerts.slice(0, 8)} loading={alertsLoading} />
                    </GlassCard>

                    {/* Top actualités */}
                    <GlassCard animate className="p-5">
                      <div className="flex items-center gap-2 mb-4">
                        <Newspaper size={15} className="text-cyan-400" />
                        <h3
                          className="text-base font-semibold"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          Actualités à fort impact
                        </h3>
                        <button
                          onClick={() => setActiveTab('enriched')}
                          className="ml-auto text-sm transition-colors flex items-center gap-0.5"
                          style={{ color: '#0EA5E9' }}
                        >
                          Voir tout <ChevronRight size={12} />
                        </button>
                      </div>
                      <EnrichedNewsFeed
                        articles={enrichedNews.slice(0, 5)}
                        loading={enrichedLoading}
                      />
                    </GlassCard>
                  </div>

                  {/* Mini carte causale */}
                  {kgSnapshot && kgSnapshot.nodes.length > 0 && (
                    <GlassCard animate className="p-5">
                      <div className="flex items-center gap-2 mb-4">
                        <GitBranch size={15} className="text-violet-400" />
                        <h3
                          className="text-base font-semibold"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          Carte causale — Aperçu Talan
                        </h3>
                        <span className="text-xs text-[var(--text-faint)] ml-2">
                          {kgStats?.total_nodes ?? '—'} entités · {kgStats?.total_relations ?? '—'} liens
                        </span>
                        <button
                          onClick={() => setActiveTab('kg')}
                          className="ml-auto text-sm transition-colors flex items-center gap-0.5"
                          style={{ color: '#8B5CF6' }}
                        >
                          Explorer <ChevronRight size={12} />
                        </button>
                      </div>
                      <ErrorBoundary>
                        <KGReadableGraph
                          snapshot={kgSnapshot}
                          stats={kgStats}
                          loading={kgLoading || kgStatsLoading}
                          centerCompany={centerCompany}
                          onCompanyChange={setCenterCompany}
                        />
                      </ErrorBoundary>
                    </GlassCard>
                  )}
                </>
              )}

              {/* ── VEILLE ────────────────────────────────────────────────────── */}
              {activeTab === 'enriched' && (
                <GlassCard animate className="p-5">
                  {/* Sub-toggle: Actualités / Analyses IA */}
                  <div className="flex items-center gap-3 mb-5 flex-wrap">
                    <Newspaper size={16} className="text-cyan-400" />
                    <h3
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Veille marché
                    </h3>

                    <div
                      className="flex rounded-xl overflow-hidden ml-4"
                      style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-base)' }}
                    >
                      {([
                        { id: 'news' as const,     label: `Actualités enrichies (${enrichedNews.length})` },
                        { id: 'analyses' as const, label: `Analyses IA (${analyses.length})` },
                      ]).map(({ id, label }, i, arr) => (
                        <button
                          key={id}
                          onClick={() => setVeilleSubTab(id)}
                          className="px-3 py-1.5 text-xs font-semibold transition-all"
                          style={{
                            background: veilleSubTab === id ? '#0EA5E915' : 'transparent',
                            color: veilleSubTab === id ? '#0EA5E9' : 'var(--text-muted)',
                            borderRight: i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                          }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>

                    {veilleSubTab === 'news' && (
                      <button
                        onClick={() => { setEnrichedLive(true); refetchEnriched(); }}
                        disabled={enrichedFetching}
                        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all"
                        style={{
                          background: 'var(--bg-base)',
                          color: 'var(--text-muted)',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <RefreshCw size={11} className={enrichedFetching ? 'animate-spin' : ''} />
                        {enrichedFetching ? 'Chargement…' : 'Actualiser en direct'}
                      </button>
                    )}
                    {veilleSubTab === 'analyses' && (
                      <button
                        onClick={() =>
                          queryClient.invalidateQueries({ queryKey: ['market', 'analyses'] })
                        }
                        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all"
                        style={{
                          background: 'var(--bg-base)',
                          color: 'var(--text-muted)',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <RefreshCw size={11} />
                        Actualiser
                      </button>
                    )}
                  </div>

                  {/* Contextual explanation for Analyses IA */}
                  {veilleSubTab === 'analyses' && (
                    <div
                      className="flex items-start gap-2 px-3 py-2.5 rounded-xl mb-4 text-xs"
                      style={{ background: '#F5F3FF', border: '1px solid #DDD6FE', color: '#5B21B6' }}
                    >
                      <FlaskConical size={13} className="mt-0.5 flex-shrink-0" />
                      <p>
                        <strong>Comment c'est généré :</strong> chaque article est envoyé au LLM qui
                        extrait entités, relations causales et score d'impact sur Talan.
                        Ces relations alimentent directement la Carte causale et les Signaux IA.
                      </p>
                    </div>
                  )}

                  {veilleSubTab === 'news' && (
                    <EnrichedNewsFeed
                      articles={enrichedNews}
                      loading={enrichedLoading}
                      onRefresh={() => { setEnrichedLive(true); refetchEnriched(); }}
                      refreshing={enrichedFetching}
                    />
                  )}
                  {veilleSubTab === 'analyses' && (
                    <NewsAnalysesFeed analyses={analyses} loading={false} />
                  )}
                </GlassCard>
              )}

              {/* ── MARCHÉS ───────────────────────────────────────────────────── */}
              {activeTab === 'prices' && (
                <GlassCard animate className="p-5">
                  <div className="flex items-center gap-2 mb-5">
                    <BarChart2 size={16} className="text-emerald-400" />
                    <h3
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Marchés financiers — Snapshot temps réel
                    </h3>
                  </div>
                  <PricesTicker
                    prices={prices}
                    loading={pricesLoading}
                    onRefresh={() => refetchPrices()}
                    refreshing={pricesLoading}
                  />
                </GlassCard>
              )}

              {/* ── CARTE CAUSALE ─────────────────────────────────────────────── */}
              {activeTab === 'kg' && (
                <GlassCard animate className="p-5">
                  <div className="flex items-center gap-2 mb-5 flex-wrap">
                    <GitBranch size={16} className="text-violet-400" />
                    <h3
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Carte causale
                    </h3>
                    <span className="text-xs text-[var(--text-faint)]">
                      {kgStats?.total_nodes ?? '—'} entités · {kgStats?.total_relations ?? '—'} liens
                    </span>

                    {/* View toggle — 2D default, 3D & full as options */}
                    <div
                      className="ml-auto flex items-center rounded-xl overflow-hidden"
                      style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-base)' }}
                    >
                      {(
                        [
                          ['2d', 'Vue lisible'],
                          ['3d', 'Vue 3D'],
                          ['full', 'Graphe complet'],
                        ] as const
                      ).map(([v, label], i, arr) => (
                        <button
                          key={v}
                          onClick={() => setKgView(v)}
                          className="px-3 py-1.5 text-xs font-semibold transition-all"
                          style={{
                            background: kgView === v ? '#8B5CF615' : 'transparent',
                            color: kgView === v ? '#8B5CF6' : 'var(--text-muted)',
                            borderRight:
                              i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                          }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <ErrorBoundary>
                    {kgView === '2d' && (
                      <KGReadableGraph
                        snapshot={kgSnapshot}
                        stats={kgStats}
                        loading={kgLoading || kgStatsLoading}
                        centerCompany={centerCompany}
                        onCompanyChange={(name) => setCenterCompany(name)}
                      />
                    )}
                    {kgView === '3d' && (
                      <Suspense
                        fallback={
                          <div className="h-96 bg-[var(--border-subtle)] rounded-xl animate-pulse" />
                        }
                      >
                        <KGExplorer
                          snapshot={kgSnapshot}
                          stats={kgStats}
                          hiddenRisks={hiddenRisks}
                          loading={kgLoading || kgStatsLoading || hiddenLoading}
                          centerCompany={centerCompany}
                          onCompanyChange={(name) => setCenterCompany(name)}
                        />
                      </Suspense>
                    )}
                    {kgView === 'full' && (
                      <FullGraphViewer
                        snapshot={kgFull}
                        loading={kgFullLoading}
                        onRefresh={refetchKGFull}
                        refreshing={kgFullFetching}
                      />
                    )}
                  </ErrorBoundary>
                </GlassCard>
              )}

              {/* ── SIGNAUX IA ────────────────────────────────────────────────── */}
              {activeTab === 'gnn' && (
                <GlassCard animate className="p-5">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <Brain size={16} className="text-violet-400" />
                    <h3
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Signaux IA — Prédictions de propagation
                    </h3>
                    <span
                      className="text-[11px] px-2 py-0.5 rounded-full ml-1"
                      style={{ background: '#F5F3FF', color: '#6D28D9' }}
                    >
                      TGAT · AUC 0.9227
                    </span>
                  </div>

                  {/* How it connects to the rest */}
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-xl mb-4 text-xs flex-wrap"
                    style={{ background: '#F5F3FF', border: '1px solid #DDD6FE', color: '#5B21B6' }}
                  >
                    <Brain size={12} className="flex-shrink-0" />
                    <span>
                      Le modèle analyse la <strong>Carte causale</strong> et calcule comment chaque
                      événement se propage jusqu'à Talan. Cliquez sur une barre ou une ligne pour
                      voir le chemin détaillé et la recommandation associée.
                    </span>
                    <button
                      onClick={() => setActiveTab('recommend')}
                      className="ml-auto flex items-center gap-1 font-bold whitespace-nowrap hover:gap-1.5 transition-all"
                      style={{ color: '#7C3AED' }}
                    >
                      Voir le plan d'action <ChevronRight size={12} />
                    </button>
                  </div>

                  <GNNPredictions
                    result={gnnResult}
                    loading={gnnLoading}
                    onRunGNN={handleRunGNN}
                    running={runningGNN}
                  />
                </GlassCard>
              )}

              {/* ── PLAN D'ACTION ─────────────────────────────────────────────── */}
              {activeTab === 'recommend' && (
                <GlassCard animate className="p-5">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <Lightbulb size={16} className="text-amber-500" />
                    <h3
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Plan d'action stratégique
                    </h3>
                    <span
                      className="text-[11px] px-2 py-0.5 rounded-full ml-1"
                      style={{ background: '#FEF3C7', color: '#92400E' }}
                    >
                      GNN + LSTM + LLM
                    </span>
                  </div>

                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-xl mb-4 text-xs flex-wrap"
                    style={{ background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E' }}
                  >
                    <Lightbulb size={12} className="flex-shrink-0" />
                    <span>
                      Recommandations générées à partir des <strong>Signaux IA</strong> (GNN) et
                      des prévisions LSTM 7j/30j. Cliquez sur "Générer" pour lancer une nouvelle
                      analyse complète.
                    </span>
                    <button
                      onClick={() => setActiveTab('gnn')}
                      className="ml-auto flex items-center gap-1 font-bold whitespace-nowrap hover:gap-1.5 transition-all"
                      style={{ color: '#B45309' }}
                    >
                      Voir les Signaux IA <ChevronRight size={12} />
                    </button>
                  </div>

                  <StrategicRecommendations
                    result={recResult}
                    forecast={forecastResult ?? null}
                    loading={forecastLoading}
                    onGenerate={handleGenerateRec}
                    generating={generatingRec}
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
