/**
 * KGExplorer — Neurological World Model Visualizer (3D)
 *
 * Light-theme 3D graph visualization of the Talan intelligence Knowledge Graph.
 *
 * Features:
 *  - Light gray background, dark saturated node colors for readability
 *  - Relations visible with thick opaque colored links + directional arrows
 *  - Relation type shown as tooltip on link hover
 *  - Node size driven by degree + PageRank weight
 *  - Hover tooltip with entity details
 *  - Click → camera fly-to + neighbor highlight
 *  - Search by name / filter by entity type
 *  - PageRank simulation button
 *  - Hidden risks panel
 */
import {
  useRef, useCallback, useEffect, useState, useMemo, lazy, Suspense,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  GitBranch, AlertTriangle, Search, ZoomIn, ZoomOut,
  Maximize2, Filter, Activity, Brain, X, ExternalLink,
  TrendingDown, TrendingUp, Minus,
} from 'lucide-react';
import type { KGSnapshot, KGStats, HiddenRisk } from '../../api/marketAnalysisApi';
import { marketAnalysisApi } from '../../api/marketAnalysisApi';

// ── Lazy-load ForceGraph3D (heavy WebGL bundle) ───────────────────────────────
const ForceGraph3D = lazy(() => import('react-force-graph-3d'));

// ── Visual config ─────────────────────────────────────────────────────────────

const NODE_CONFIG: Record<string, { color: string; emissive: string; label: string }> = {
  Company:        { color: '#0284C7', emissive: '#0EA5E9', label: 'Entreprise' },
  Person:         { color: '#BE185D', emissive: '#EC4899', label: 'Personne' },
  Technology:     { color: '#059669', emissive: '#10B981', label: 'Technologie' },
  Regulation:     { color: '#C2410C', emissive: '#F97316', label: 'Réglementation' },
  Competitor:     { color: '#DC2626', emissive: '#EF4444', label: 'Concurrent' },
  MarketTrend:    { color: '#7C3AED', emissive: '#A855F7', label: 'Tendance Marché' },
  Sector:         { color: '#4338CA', emissive: '#6366F1', label: 'Secteur' },
  Country:        { color: '#15803D', emissive: '#22C55E', label: 'Pays' },
  Event:          { color: '#B45309', emissive: '#F59E0B', label: 'Événement' },
  MacroIndicator: { color: '#A21CAF', emissive: '#D946EF', label: 'Indicateur Macro' },
  News:           { color: '#475569', emissive: '#64748B', label: 'Actualité' },
  Default:        { color: '#64748B', emissive: '#94A3B8', label: 'Autre' },
};

const ALL_TYPES = Object.keys(NODE_CONFIG).filter((k) => k !== 'Default');

function nodeColor(label: string): string {
  return (NODE_CONFIG[label] ?? NODE_CONFIG.Default).color;
}

function linkParticleColor(score?: number | null): string {
  if (score === null || score === undefined) return '#64748B';
  if (score <= -0.5) return '#DC2626';
  if (score  <  0)   return '#EA580C';
  if (score  >= 0.5) return '#059669';
  if (score  >  0)   return '#0284C7';
  return '#64748B';
}

function linkColor(score?: number | null): string {
  if (score === null || score === undefined) return 'rgba(100,116,139,0.6)';
  if (score <= -0.5) return 'rgba(220,38,38,0.85)';
  if (score  <  0)   return 'rgba(234,88,12,0.75)';
  if (score  >= 0.5) return 'rgba(5,150,105,0.85)';
  if (score  >  0)   return 'rgba(2,132,199,0.75)';
  return 'rgba(100,116,139,0.6)';
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface GraphNode {
  id:    string;
  name:  string;
  slug:  string;
  label: string;
  ticker?: string;
  val:   number;           // node size
  color: string;
  properties?: Record<string, unknown>;
  __degree?: number;
  __pr?: number;           // PageRank score
}

interface GraphLink {
  source: string;
  target: string;
  type:   string;
  impact_score?:    number | null;
  sentiment?:       number | null;
  confidence?:      number | null;
  causality_score?: number | null;
  reason?:          string | null;
  evidence?:        string | null;
  time_horizon?:    string | null;
  talan_relevant?:  boolean | null;
  color:  string;
}

interface TooltipState {
  x:    number;
  y:    number;
  node: GraphNode;
}

interface Props {
  snapshot:        KGSnapshot | undefined;
  stats:           KGStats | undefined;
  hiddenRisks:     HiddenRisk[];
  loading:         boolean;
  centerCompany:   string;
  onCompanyChange: (name: string) => void;
}

// ── Tooltip card ──────────────────────────────────────────────────────────────

function NodeTooltip({ tooltip }: { tooltip: TooltipState }) {
  const cfg = NODE_CONFIG[tooltip.node.label] ?? NODE_CONFIG.Default;
  return (
    <div
      className="fixed z-50 pointer-events-none"
      style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.92 }}
        transition={{ duration: 0.12 }}
        className="rounded-2xl p-3.5 shadow-xl min-w-[200px] max-w-[280px]"
        style={{
          background: 'rgba(255,255,255,0.97)',
          border: `1px solid ${cfg.color}50`,
          backdropFilter: 'blur(12px)',
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{ background: cfg.color }}
          />
          <span className="font-semibold text-sm truncate" style={{ color: '#1E293B' }}>{tooltip.node.name}</span>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">Type</span>
            <span style={{ color: cfg.color }} className="font-medium">{cfg.label}</span>
          </div>
          {tooltip.node.ticker && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Ticker</span>
              <span className="font-mono" style={{ color: '#059669' }}>{tooltip.node.ticker}</span>
            </div>
          )}
          {tooltip.node.label === 'Event' && (tooltip.node.properties?.event_type as string) && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Catégorie</span>
              <span className="font-medium" style={{ color: '#B45309' }}>
                {(tooltip.node.properties?.event_type as string).replace(/_/g, ' ')}
              </span>
            </div>
          )}
          {tooltip.node.label === 'Event' && (tooltip.node.properties?.date as string) && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Date</span>
              <span className="font-mono" style={{ color: '#475569' }}>
                {(tooltip.node.properties?.date as string).slice(0, 10)}
              </span>
            </div>
          )}
          {tooltip.node.label === 'Event' && (tooltip.node.properties?.target_impact_talan as number) != null && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Impact Talan</span>
              <span className="font-mono font-semibold" style={{
                color: (tooltip.node.properties?.target_impact_talan as number) >= 0 ? '#059669' : '#DC2626',
              }}>
                {((tooltip.node.properties?.target_impact_talan as number) >= 0 ? '+' : '')}
                {(tooltip.node.properties?.target_impact_talan as number)?.toFixed(2)}
              </span>
            </div>
          )}
          {tooltip.node.__degree !== undefined && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Connexions</span>
              <span className="font-mono font-semibold" style={{ color: '#1E293B' }}>{tooltip.node.__degree}</span>
            </div>
          )}
          {tooltip.node.__pr !== undefined && tooltip.node.__pr > 0 && (
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">PageRank</span>
              <span className="font-mono" style={{ color: '#7C3AED' }}>{tooltip.node.__pr.toFixed(3)}</span>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}

// ── Selected node sidebar ──────────────────────────────────────────────────────

function NodeDetailPanel({
  node,
  links,
  nodes,
  onClose,
  onCenter,
}: {
  node:     GraphNode;
  links:    GraphLink[];
  nodes:    GraphNode[];
  onClose:  () => void;
  onCenter: (name: string) => void;
}) {
  const cfg = NODE_CONFIG[node.label] ?? NODE_CONFIG.Default;
  const nodeLinks = links.filter(
    (l) => l.source === node.id || l.target === node.id
  );

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.97)',
        border: `1px solid ${cfg.color}40`,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.10)',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 p-3.5 pb-3"
        style={{ borderBottom: `1px solid ${cfg.color}20` }}>
        <div
          className="w-4 h-4 rounded-full flex-shrink-0"
          style={{ background: cfg.color }}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate" style={{ color: '#1E293B' }}>{node.name}</p>
          <p className="text-xs font-medium" style={{ color: cfg.color }}>{cfg.label}</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onCenter(node.name)}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: cfg.color }}
            title="Centrer le graphe sur ce nœud"
          >
            <Maximize2 size={12} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 transition-colors"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="p-3 space-y-1.5">
        {node.ticker && (
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">Ticker</span>
            <span className="font-mono font-semibold" style={{ color: '#059669' }}>{node.ticker}</span>
          </div>
        )}
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Connexions</span>
          <span className="font-mono font-semibold" style={{ color: '#1E293B' }}>{node.__degree ?? nodeLinks.length}</span>
        </div>
        {node.__pr !== undefined && node.__pr > 0 && (
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">PageRank</span>
            <span className="font-mono" style={{ color: '#7C3AED' }}>{node.__pr.toFixed(3)}</span>
          </div>
        )}
      </div>

      {/* Relations */}
      {nodeLinks.length > 0 && (
        <div className="p-3 pt-0">
          <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">
            Relations ({nodeLinks.length})
          </p>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {nodeLinks.slice(0, 10).map((l, i) => {
              const isFrom = l.source === node.id;
              const otherId  = isFrom ? l.target : l.source;
              const otherNode = nodes.find((n) => n.id === otherId);
              const sc = l.impact_score;
              const scColor = sc == null ? '#64748B'
                : sc < 0 ? '#DC2626' : sc > 0 ? '#059669' : '#64748B';
              return (
                <div key={i}
                  className="flex items-center gap-1.5 px-2 py-1.5 rounded-xl"
                  style={{ background: 'rgba(100,116,139,0.07)' }}
                >
                  <span className="text-[10px] text-slate-400 flex-shrink-0 w-3">
                    {isFrom ? '→' : '←'}
                  </span>
                  <span className="text-xs text-slate-700 truncate flex-1">
                    {otherNode?.name ?? otherId}
                  </span>
                  <span
                    className="text-[9px] px-1.5 py-0.5 rounded-md font-semibold flex-shrink-0"
                    style={{ background: `${scColor}18`, color: scColor }}
                  >
                    {l.type.replace(/_/g, ' ')}
                  </span>
                  {sc != null && (
                    <span className="text-[10px] font-mono flex-shrink-0 font-semibold" style={{ color: scColor }}>
                      {sc >= 0 ? '+' : ''}{sc.toFixed(2)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function KGExplorer({
  snapshot, stats, hiddenRisks, loading, centerCompany, onCompanyChange,
}: Props) {
  const fgRef = useRef<any>(null);

  const [selected,    setSelected]    = useState<GraphNode | null>(null);
  const [hovered,     setHovered]     = useState<GraphNode | null>(null);
  const [tooltip,     setTooltip]     = useState<TooltipState | null>(null);
  const [searchVal,   setSearchVal]   = useState('');
  const [typeFilter,  setTypeFilter]  = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set());
  const [prScores,    setPrScores]    = useState<Record<string, number>>({});
  const [prLoading,   setPrLoading]   = useState(false);
  const [showLegend,  setShowLegend]  = useState(true);

  // ── Build graph data ───────────────────────────────────────────────────────

  const rawNodes = snapshot?.nodes ?? [];
  const rawEdges = snapshot?.edges ?? [];

  // Compute degree map
  const degreeMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const e of rawEdges) {
      map[e.from] = (map[e.from] ?? 0) + 1;
      map[e.to]   = (map[e.to]   ?? 0) + 1;
    }
    return map;
  }, [rawEdges]);

  const nodes: GraphNode[] = useMemo(() => {
    return rawNodes
      .filter((n) => !typeFilter || (n.labels ?? [])[0] === typeFilter)
      .map((n) => {
        const label  = (n.labels ?? ['Company'])[0];
        const degree = degreeMap[n.id] ?? 1;
        const pr     = prScores[n.slug ?? n.name] ?? 0;
        const isCenter = n.name === centerCompany;
        // Node size: center=20, by degree + pagerank boost
        const baseSize = isCenter ? 20 : Math.max(4, Math.min(15, degree * 1.5 + pr * 30));
        return {
          id:         n.id,
          name:       n.name,
          slug:       n.slug ?? n.name.toLowerCase(),
          label,
          ticker:     n.ticker,
          color:      nodeColor(label),
          val:        baseSize,
          properties: (n as any).properties,
          __degree:   degree,
          __pr:       pr,
        };
      });
  }, [rawNodes, degreeMap, prScores, typeFilter, centerCompany]);

  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);

  const links: GraphLink[] = useMemo(() => {
    return rawEdges
      .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to))
      .map((e) => ({
        source:          e.from,
        target:          e.to,
        type:            e.type,
        impact_score:    e.impact_score,
        sentiment:       (e as any).sentiment,
        confidence:      e.confidence,
        causality_score: (e as any).causality_score,
        reason:          e.reason,
        evidence:        (e as any).evidence,
        time_horizon:    (e as any).time_horizon,
        talan_relevant:  (e as any).talan_relevant,
        color:           linkColor(e.impact_score),
      }));
  }, [rawEdges, nodeIds]);

  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  // ── Auto fit on load ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!fgRef.current || !nodes.length) return;
    const t = setTimeout(() => {
      fgRef.current?.zoomToFit(600, 80);
    }, 800);
    return () => clearTimeout(t);
  }, [nodes.length]);

  // ── Node click — camera fly + highlight ───────────────────────────────────
  const handleNodeClick = useCallback((node: any) => {
    setSelected(node as GraphNode);
    // Highlight neighbors
    const neighborIds = new Set<string>([node.id]);
    for (const l of links) {
      if (l.source === node.id) neighborIds.add(l.target as string);
      if (l.target === node.id) neighborIds.add(l.source as string);
    }
    setHighlighted(neighborIds);
    // Camera fly-to
    if (fgRef.current) {
      const distance = 120;
      const { x = 0, y = 0, z = 0 } = node;
      fgRef.current.cameraPosition(
        { x: x + distance, y: y + distance * 0.5, z: z + distance },
        { x, y, z },
        1200,
      );
    }
  }, [links]);

  const handleBackgroundClick = useCallback(() => {
    setSelected(null);
    setHighlighted(new Set());
  }, []);

  // ── Hover ─────────────────────────────────────────────────────────────────
  const handleNodeHover = useCallback((node: any, _prev: any, ev?: MouseEvent) => {
    if (node) {
      setHovered(node as GraphNode);
      setTooltip({
        x:    ev?.clientX ?? 0,
        y:    ev?.clientY ?? 0,
        node: node as GraphNode,
      });
    } else {
      setHovered(null);
      setTooltip(null);
    }
  }, []);

  // Track mouse for tooltip position
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (hovered) {
        setTooltip((prev) => prev ? { ...prev, x: e.clientX, y: e.clientY } : null);
      }
    };
    window.addEventListener('mousemove', onMove);
    return () => window.removeEventListener('mousemove', onMove);
  }, [hovered]);

  // ── PageRank simulation ────────────────────────────────────────────────────
  const handlePageRank = useCallback(async () => {
    setPrLoading(true);
    try {
      const res = await marketAnalysisApi.getPageRank(40);
      const map: Record<string, number> = {};
      for (const entry of res.data) {
        map[entry.slug] = entry.score;
        map[entry.name] = entry.score; // also by name for fallback
      }
      setPrScores(map);
    } catch (e) {
      console.error('PageRank failed', e);
    } finally {
      setPrLoading(false);
    }
  }, []);

  // ── Search ────────────────────────────────────────────────────────────────
  const handleSearch = useCallback(() => {
    const q = searchVal.trim();
    if (!q) return;
    // Try to find node by name and fly to it
    const found = nodes.find((n) => n.name.toLowerCase().includes(q.toLowerCase()));
    if (found && fgRef.current) {
      handleNodeClick(found);
      setSearchVal('');
    } else {
      // Fall back to centering the graph on a new company
      onCompanyChange(q);
      setSearchVal('');
    }
  }, [searchVal, nodes, handleNodeClick, onCompanyChange]);

  // ── Node paint (opacity based on highlight) ────────────────────────────────
  const nodeThreeObject = useCallback((node: any) => {
    // We rely on default sphere geometry — just override opacity via color
    return undefined; // use default
  }, []);

  // Node opacity: dim non-highlighted when selection active
  const getNodeColor = useCallback((node: any) => {
    if (highlighted.size === 0) return node.color;
    return highlighted.has(node.id) ? node.color : `${node.color}33`;
  }, [highlighted]);

  const getLinkColor = useCallback((link: any) => {
    if (highlighted.size === 0) return link.color;
    const src = typeof link.source === 'object' ? link.source.id : link.source;
    const tgt = typeof link.target === 'object' ? link.target.id : link.target;
    return (highlighted.has(src) && highlighted.has(tgt)) ? link.color : `rgba(100,116,139,0.08)`;
  }, [highlighted]);

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div
        className="flex items-center justify-center rounded-2xl overflow-hidden"
        style={{ height: 560, background: '#F8FAFC', border: '1px solid rgba(148,163,184,0.2)' }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="relative w-12 h-12">
            <div className="absolute inset-0 rounded-full border-2 border-sky-400/40 animate-ping" />
            <div className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(2,132,199,0.08)' }}>
              <GitBranch size={22} style={{ color: '#0284C7' }} />
            </div>
          </div>
          <p className="text-sm font-medium" style={{ color: '#0284C7' }}>Chargement du Knowledge Graph 3D…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* ── Controls bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Search */}
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-xl flex-1 min-w-[200px]"
          style={{ background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(148,163,184,0.25)' }}
        >
          <Search size={13} className="text-slate-400 flex-shrink-0" />
          <input
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder={`Rechercher… (centre: ${centerCompany})`}
            className="bg-transparent outline-none text-sm placeholder-slate-400 w-full" style={{ color: '#1E293B' }}
          />
        </div>

        {/* Type filter */}
        <div className="flex items-center gap-1 flex-wrap">
          {[null, ...ALL_TYPES.slice(0, 6)].map((t) => {
            const cfg = t ? NODE_CONFIG[t] : null;
            const active = typeFilter === t;
            return (
              <button
                key={t ?? 'all'}
                onClick={() => setTypeFilter(active ? null : t)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-[10px] font-semibold transition-all"
                style={{
                  background: active
                    ? (cfg ? `${cfg.color}18` : 'rgba(2,132,199,0.12)')
                    : 'rgba(255,255,255,0.85)',
                  color: active ? (cfg?.color ?? '#0284C7') : '#64748B',
                  border: `1px solid ${active ? (cfg?.color ?? '#0284C7') + '50' : 'rgba(148,163,184,0.25)'}`,
                }}
              >
                {t ? (
                  <>
                    <span
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: cfg?.color }}
                    />
                    {cfg?.label ?? t}
                  </>
                ) : (
                  <><Filter size={9} /> Tous</>
                )}
              </button>
            );
          })}
        </div>

        {/* Zoom / fit buttons */}
        {[
          { icon: <ZoomIn size={13} />,    action: () => fgRef.current?.zoom(1.4, 300),        tip: 'Zoom +' },
          { icon: <ZoomOut size={13} />,   action: () => fgRef.current?.zoom(0.7, 300),        tip: 'Zoom -' },
          { icon: <Maximize2 size={13} />, action: () => fgRef.current?.zoomToFit(600, 80),    tip: 'Ajuster' },
        ].map(({ icon, action, tip }) => (
          <button
            key={tip}
            onClick={action}
            title={tip}
            className="w-8 h-8 rounded-xl flex items-center justify-center transition-all"
            style={{ background: 'rgba(255,255,255,0.9)', color: '#64748B', border: '1px solid rgba(148,163,184,0.25)' }}
          >
            {icon}
          </button>
        ))}

        {/* PageRank simulation */}
        <button
          onClick={handlePageRank}
          disabled={prLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all"
          style={{
            background: prLoading ? 'rgba(124,58,237,0.08)' : 'rgba(124,58,237,0.12)',
            color: '#7C3AED',
            border: '1px solid rgba(124,58,237,0.35)',
          }}
        >
          <Brain size={12} className={prLoading ? 'animate-pulse' : ''} />
          {prLoading ? 'Calcul…' : 'PageRank'}
        </button>
      </div>

      {/* ── Graph + sidebar ────────────────────────────────────────────────── */}
      <div className="flex gap-3 relative">
        {/* 3D Graph canvas */}
        <div
          className="flex-1 rounded-2xl overflow-hidden relative"
          style={{ height: 560, background: '#F8FAFC', border: '1px solid rgba(148,163,184,0.2)' }}
        >
          {/* Stats overlay */}
          <div
            className="absolute top-3 left-3 z-10 flex items-center gap-3 px-3 py-2 rounded-xl text-xs"
            style={{ background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(148,163,184,0.25)', boxShadow: '0 1px 8px rgba(0,0,0,0.07)' }}
          >
            <div className="flex items-center gap-1.5">
              <Activity size={11} style={{ color: '#0284C7' }} />
              <span className="font-mono font-semibold" style={{ color: '#0284C7' }}>{nodes.length}</span>
              <span className="text-slate-500">nœuds</span>
            </div>
            <div className="w-px h-3 bg-slate-200" />
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-semibold" style={{ color: '#7C3AED' }}>{links.length}</span>
              <span className="text-slate-500">relations</span>
            </div>
            {Object.keys(prScores).length > 0 && (
              <>
                <div className="w-px h-3 bg-slate-200" />
                <span className="font-medium text-[10px]" style={{ color: '#7C3AED' }}>PageRank actif</span>
              </>
            )}
          </div>

          {/* Legend toggle */}
          <button
            onClick={() => setShowLegend(!showLegend)}
            className="absolute top-3 right-3 z-10 px-2.5 py-1.5 rounded-xl text-[10px] font-medium"
            style={{
              background: 'rgba(255,255,255,0.92)',
              color: '#64748B',
              border: '1px solid rgba(148,163,184,0.25)',
              boxShadow: '0 1px 8px rgba(0,0,0,0.07)',
            }}
          >
            {showLegend ? 'Masquer légende' : 'Légende'}
          </button>

          {nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <GitBranch size={36} className="text-slate-300" />
              <p className="text-sm font-semibold" style={{ color: '#475569' }}>Knowledge Graph vide</p>
              <p className="text-xs text-slate-400">Lancez un cycle pour peupler le graphe</p>
            </div>
          ) : (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm animate-pulse" style={{ color: '#0284C7' }}>Initialisation 3D…</div>
                </div>
              }
            >
              <ForceGraph3D
                ref={fgRef}
                graphData={graphData}
                backgroundColor="#F8FAFC"
                // Node appearance
                nodeLabel=""
                nodeColor={getNodeColor}
                nodeVal={(n: any) => n.val}
                nodeOpacity={0.95}
                nodeResolution={16}
                // Link appearance — thick, opaque, with arrows + relation type tooltip
                linkLabel={(l: any) => l.type?.replace(/_/g, ' ') ?? ''}
                linkColor={getLinkColor}
                linkWidth={(l: any) => Math.max(1.5, Math.abs(l.impact_score ?? 0.2) * 4)}
                linkOpacity={0.9}
                linkDirectionalArrowLength={5}
                linkDirectionalArrowRelPos={1}
                linkDirectionalArrowColor={getLinkColor}
                linkDirectionalParticles={(l: any) => (
                  Math.abs(l.impact_score ?? 0) > 0.2 ? 4 : 2
                )}
                linkDirectionalParticleWidth={(l: any) => (
                  Math.max(1.5, Math.abs(l.impact_score ?? 0.2) * 3)
                )}
                linkDirectionalParticleColor={(l: any) => linkParticleColor(l.impact_score)}
                linkDirectionalParticleSpeed={0.006}
                // Interaction
                onNodeClick={handleNodeClick}
                onNodeHover={handleNodeHover as any}
                onBackgroundClick={handleBackgroundClick}
                // Physics
                d3AlphaDecay={0.018}
                d3VelocityDecay={0.28}
                cooldownTicks={120}
                warmupTicks={30}
              />
            </Suspense>
          )}
        </div>

        {/* Right sidebar */}
        <div className="w-56 flex-shrink-0 flex flex-col gap-3">
          <AnimatePresence>
            {selected && (
              <NodeDetailPanel
                key={selected.id}
                node={selected}
                links={links}
                nodes={nodes}
                onClose={() => { setSelected(null); setHighlighted(new Set()); }}
                onCenter={onCompanyChange}
              />
            )}
          </AnimatePresence>

          {/* Legend */}
          <AnimatePresence>
            {showLegend && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="rounded-2xl p-3"
                style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.2)', boxShadow: '0 1px 8px rgba(0,0,0,0.06)' }}
              >
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
                  Légende des nœuds
                </p>
                <div className="space-y-1.5">
                  {ALL_TYPES.filter((t) => t !== 'News').map((label) => {
                    const cfg = NODE_CONFIG[label];
                    const active = typeFilter === label;
                    return (
                      <button
                        key={label}
                        onClick={() => setTypeFilter(active ? null : label)}
                        className="flex items-center gap-2 w-full hover:opacity-80 transition-opacity"
                      >
                        <div
                          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{
                            background: cfg.color,
                            boxShadow: active ? `0 0 4px ${cfg.color}` : 'none',
                          }}
                        />
                        <span className="text-[11px] text-left font-medium" style={{ color: active ? cfg.color : '#64748B' }}>{cfg.label}</span>
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* KG Stats */}
          {stats && (
            <div
              className="rounded-2xl p-3 space-y-2"
              style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.2)', boxShadow: '0 1px 8px rgba(0,0,0,0.06)' }}
            >
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
                Statistiques KG
              </p>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Total nœuds</span>
                  <span className="font-mono font-semibold" style={{ color: '#0284C7' }}>{stats.total_nodes.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Total relations</span>
                  <span className="font-mono font-semibold" style={{ color: '#7C3AED' }}>{stats.total_relations.toLocaleString()}</span>
                </div>
                {Object.entries(stats.nodes_by_label ?? {})
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 8)
                  .map(([label, count]) => {
                    const cfg = NODE_CONFIG[label];
                    return (
                      <div key={label} className="flex justify-between text-[11px]">
                        <div className="flex items-center gap-1.5">
                          {cfg && (
                            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                              style={{ background: cfg.color }} />
                          )}
                          <span className="text-slate-500">{label}</span>
                        </div>
                        <span className="text-slate-500 font-mono">{count}</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {tooltip && <NodeTooltip tooltip={tooltip} />}
      </AnimatePresence>

      {/* ── Hidden risks panel ────────────────────────────────────────────── */}
      {hiddenRisks.length > 0 && (
        <div
          className="rounded-2xl p-4"
          style={{
            background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.18)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-red-400" />
            <p className="text-sm font-semibold text-red-400">
              Risques cachés détectés par GNN
            </p>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{ background: 'rgba(239,68,68,0.2)', color: '#FCA5A5' }}
            >
              {hiddenRisks.length}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
            {hiddenRisks.slice(0, 6).map((r, i) => {
              const score  = r.chain_score ?? 0;
              const isNeg  = score < 0;
              const ImpIcon = isNeg ? TrendingDown : score > 0 ? TrendingUp : Minus;
              return (
                <div
                  key={i}
                  className="flex items-start gap-3 p-3 rounded-xl"
                  style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid rgba(239,68,68,0.12)' }}
                >
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
                    style={{ background: 'rgba(239,68,68,0.15)', color: '#FCA5A5' }}
                  >
                    {r.hops}↑
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white truncate">{r.source}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <ImpIcon size={10} style={{ color: isNeg ? '#F87171' : '#4ADE80' }} />
                      <span
                        className="text-[10px] font-mono"
                        style={{ color: isNeg ? '#F87171' : '#4ADE80' }}
                      >
                        {score >= 0 ? '+' : ''}{score.toFixed(2)}
                      </span>
                      <span className="text-[10px] text-slate-600">{r.source_type}</span>
                    </div>
                    {r.reasons?.[0] && (
                      <p className="text-[10px] text-slate-600 mt-0.5 line-clamp-2">
                        {r.reasons[0]}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
