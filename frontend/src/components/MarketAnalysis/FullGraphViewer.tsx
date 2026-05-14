/**
 * FullGraphViewer — 2D force-directed graph showing ALL Neo4j nodes.
 * Uses react-force-graph-2d for performance with 1000+ nodes.
 *
 * Features:
 *  - All node types color-coded (14 types)
 *  - Filter chips by node type
 *  - Stats bar (total nodes / edges / types)
 *  - Search by name
 *  - Click node → detail tooltip
 *  - Zoom controls
 */
import {
  useRef, useCallback, useMemo, useState, useEffect, lazy, Suspense,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, X, ZoomIn, ZoomOut, Maximize2, RefreshCw,
  GitBranch, Filter,
} from 'lucide-react';
import type { KGSnapshot } from '../../api/marketAnalysisApi';

const ForceGraph2D = lazy(() => import('react-force-graph-2d'));

// ── Color palette (one color per Neo4j label) ─────────────────────────────────

const NODE_COLORS: Record<string, string> = {
  Company:        '#0284C7',
  Competitor:     '#DC2626',
  Sector:         '#4338CA',
  Country:        '#15803D',
  Regulation:     '#C2410C',
  MacroIndicator: '#A21CAF',
  Event:          '#B45309',
  BusinessUnit:   '#0D9488',
  Department:     '#0D9488',
  Account:        '#EA580C',
  Project:        '#7C3AED',
  Person:         '#BE185D',
  Technology:     '#059669',
  MarketTrend:    '#6366F1',
  Default:        '#64748B',
};

const NODE_LABELS: Record<string, string> = {
  Company:        'Entreprise',
  Competitor:     'Concurrent',
  Sector:         'Secteur',
  Country:        'Pays / Géo',
  Regulation:     'Réglementation',
  MacroIndicator: 'Indicateur Macro',
  Event:          'Événement',
  BusinessUnit:   'Business Unit',
  Department:     'Département',
  Account:        'Client (Account)',
  Project:        'Projet',
  Person:         'Personne',
  Technology:     'Technologie',
  MarketTrend:    'Tendance Marché',
};

function nodeColor(labels: string[]): string {
  for (const l of (labels ?? [])) {
    if (NODE_COLORS[l]) return NODE_COLORS[l];
  }
  return NODE_COLORS.Default;
}

function nodeLabel(labels: string[]): string {
  for (const l of (labels ?? [])) {
    if (NODE_LABELS[l]) return NODE_LABELS[l];
  }
  return 'Autre';
}

function nodePrimaryLabel(labels: string[]): string {
  return (labels ?? [])[0] ?? 'Default';
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface GraphNode {
  id: string;
  name: string;
  labels: string[];
  impact_score?: number | null;
  // injected by force-graph
  x?: number;
  y?: number;
  __indexColor?: string;
}

interface GraphLink {
  source: string;
  target: string;
  type: string;
  weight?: number | null;
  impact_score?: number | null;
}

interface Props {
  snapshot: KGSnapshot | undefined;
  loading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function FullGraphViewer({ snapshot, loading, onRefresh, refreshing }: Props) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 900, h: 600 });
  const [search, setSearch] = useState('');
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  // Measure container
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDims({ w: Math.floor(width), h: Math.max(Math.floor(height), 500) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Build graph data from snapshot
  const { graphData, typeSet, typeCounts } = useMemo(() => {
    if (!snapshot?.nodes?.length) {
      return { graphData: { nodes: [], links: [] }, typeSet: new Set<string>(), typeCounts: {} as Record<string, number> };
    }

    const nodeIds = new Set(snapshot.nodes.map((n) => n.id));
    const typeCounts: Record<string, number> = {};

    const nodes: GraphNode[] = snapshot.nodes.map((n) => {
      const lbl = nodePrimaryLabel(n.labels);
      typeCounts[lbl] = (typeCounts[lbl] ?? 0) + 1;
      return {
        id: n.id,
        name: n.name ?? '?',
        labels: n.labels ?? [],
        impact_score: ((n as any).impact_score as number) ?? (n.properties?.impact_score as number) ?? null,
      };
    });

    const links: GraphLink[] = (snapshot.edges ?? [])
      .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to))
      .map((e) => ({
        source: e.from,
        target: e.to,
        type: e.type ?? '',
        weight: (e as any).weight ?? null,
        impact_score: e.impact_score ?? null,
      }));

    return {
      graphData: { nodes, links },
      typeSet: new Set(Object.keys(typeCounts)),
      typeCounts,
    };
  }, [snapshot]);

  // Initialize active types to ALL
  useEffect(() => {
    if (typeSet.size > 0 && activeTypes.size === 0) {
      setActiveTypes(new Set(typeSet));
    }
  }, [typeSet]);

  // Filtered graph data
  const filteredData = useMemo(() => {
    if (activeTypes.size === typeSet.size && !search) return graphData;

    const searchLower = search.toLowerCase();
    const filteredNodes = graphData.nodes.filter((n) => {
      const typeOk = activeTypes.has(nodePrimaryLabel(n.labels));
      const searchOk = !search || n.name.toLowerCase().includes(searchLower);
      return typeOk && searchOk;
    });
    const filteredIds = new Set(filteredNodes.map((n) => n.id));
    const filteredLinks = graphData.links.filter(
      (l) => filteredIds.has(l.source as string) && filteredIds.has(l.target as string),
    );
    return { nodes: filteredNodes, links: filteredLinks };
  }, [graphData, activeTypes, search, typeSet]);

  // Node canvas painter
  const paintNode = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const color = nodeColor(node.labels);
    const isSelected = selected?.id === node.id;
    const isHovered = hovered?.id === node.id;
    const r = isSelected ? 7 : isHovered ? 6 : 4;

    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI, false);
    ctx.fillStyle = color;
    ctx.fill();

    if (isSelected || isHovered) {
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5 / globalScale;
      ctx.stroke();
    }

    // Label only when zoomed in or selected/hovered
    if (globalScale > 2.5 || isSelected || isHovered) {
      const label = node.name.length > 22 ? node.name.slice(0, 22) + '…' : node.name;
      ctx.font = `${isSelected ? 'bold ' : ''}${Math.min(12, 3.5 / globalScale * 10)}px Inter,sans-serif`;
      ctx.fillStyle = '#1e293b';
      ctx.textAlign = 'center';
      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + 4 / globalScale);
    }
  }, [selected, hovered]);

  const toggleType = (t: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) { next.delete(t); } else { next.add(t); }
      return next;
    });
  };

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelected((prev) => prev?.id === node.id ? null : node);
    fgRef.current?.centerAt(node.x, node.y, 400);
    fgRef.current?.zoom(6, 400);
  }, []);

  if (loading || refreshing) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center animate-pulse">
          <GitBranch size={20} className="text-violet-500" />
        </div>
        <p className="text-sm text-slate-500 font-medium">Chargement du graphe complet…</p>
      </div>
    );
  }

  if (!snapshot?.nodes?.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <GitBranch size={28} className="text-slate-300" />
        <p className="text-sm text-slate-400">Aucun nœud disponible</p>
        <button onClick={onRefresh}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-200">
          <RefreshCw size={12} /> Charger
        </button>
      </div>
    );
  }

  const sortedTypes = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex flex-col gap-3">

      {/* ── Stats bar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-6 px-1 flex-wrap">
        {[
          { label: 'Nœuds total',     value: graphData.nodes.length },
          { label: 'Relations total', value: graphData.links.length },
          { label: 'Types de nœuds', value: typeSet.size },
          { label: 'Affichés',        value: filteredData.nodes.length },
        ].map(({ label, value }) => (
          <div key={label}>
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
            <p className="text-lg font-bold text-slate-700 font-mono">{value}</p>
          </div>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={onRefresh} disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200 transition-colors">
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
            Rafraîchir
          </button>
          <button onClick={() => fgRef.current?.zoomToFit(400, 40)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200 transition-colors">
            <Maximize2 size={11} />
            Tout voir
          </button>
        </div>
      </div>

      {/* ── Search + type filters ───────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un nœud…"
            className="pl-8 pr-8 py-1.5 text-xs rounded-full border border-slate-200 bg-white focus:outline-none focus:border-violet-400 w-52"
          />
          {search && (
            <button onClick={() => setSearch('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
              <X size={12} />
            </button>
          )}
        </div>

        {/* Type filters */}
        <div className="flex items-center gap-1 flex-wrap">
          <Filter size={12} className="text-slate-400 mr-0.5" />
          {sortedTypes.map(([type, count]) => {
            const active = activeTypes.has(type);
            const color = NODE_COLORS[type] ?? NODE_COLORS.Default;
            return (
              <button
                key={type}
                onClick={() => toggleType(type)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all"
                style={{
                  background: active ? `${color}18` : 'white',
                  borderColor: active ? color : '#e2e8f0',
                  color: active ? color : '#94a3b8',
                }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: active ? color : '#cbd5e1' }} />
                {NODE_LABELS[type] ?? type}
                <span className="ml-0.5 opacity-70">({count})</span>
              </button>
            );
          })}
          {activeTypes.size < typeSet.size && (
            <button onClick={() => setActiveTypes(new Set(typeSet))}
              className="px-2.5 py-1 rounded-full text-[10px] font-semibold text-violet-600 bg-violet-50 border border-violet-200">
              Tout afficher
            </button>
          )}
        </div>
      </div>

      {/* ── Graph canvas ───────────────────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
          border: '1px solid #e2e8f0',
          height: 580,
        }}
      >
        <Suspense fallback={
          <div className="flex items-center justify-center h-full">
            <div className="w-8 h-8 rounded-xl bg-violet-100 animate-pulse" />
          </div>
        }>
          <ForceGraph2D
            ref={fgRef}
            graphData={filteredData}
            width={dims.w}
            height={580}
            backgroundColor="transparent"
            nodeCanvasObject={paintNode as any}
            nodeCanvasObjectMode={() => 'replace'}
            linkColor={() => 'rgba(148,163,184,0.35)'}
            linkWidth={0.8}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkDirectionalArrowColor={() => 'rgba(148,163,184,0.5)'}
            onNodeHover={(node) => setHovered(node as GraphNode | null)}
            onNodeClick={(node) => handleNodeClick(node as GraphNode)}
            onBackgroundClick={() => setSelected(null)}
            nodeRelSize={4}
            warmupTicks={80}
            cooldownTicks={60}
            d3AlphaDecay={0.03}
            d3VelocityDecay={0.4}
          />
        </Suspense>

        {/* Zoom controls */}
        <div className="absolute bottom-4 right-4 flex flex-col gap-1.5">
          {[
            { icon: <ZoomIn size={14} />, action: () => fgRef.current?.zoom(fgRef.current.zoom() * 1.4, 200) },
            { icon: <ZoomOut size={14} />, action: () => fgRef.current?.zoom(fgRef.current.zoom() * 0.7, 200) },
            { icon: <Maximize2 size={14} />, action: () => fgRef.current?.zoomToFit(400, 40) },
          ].map(({ icon, action }, i) => (
            <button key={i} onClick={action}
              className="w-8 h-8 rounded-xl flex items-center justify-center bg-white border border-slate-200 text-slate-500 hover:bg-slate-50 shadow-sm transition-colors">
              {icon}
            </button>
          ))}
        </div>

        {/* Hint */}
        <p className="absolute bottom-4 left-4 text-[10px] text-slate-400">
          Clic sur un nœud pour centrer · Scroll pour zoomer · Double-clic pour revenir
        </p>
      </div>

      {/* ── Selected node detail ────────────────────────────────────────────── */}
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="flex items-center gap-4 p-4 rounded-2xl border"
            style={{
              background: `${nodeColor(selected.labels)}0d`,
              borderColor: `${nodeColor(selected.labels)}40`,
            }}
          >
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: nodeColor(selected.labels), opacity: 0.9 }}>
              <GitBranch size={16} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-slate-800 truncate">{selected.name}</p>
              <p className="text-xs text-slate-500">
                {nodeLabel(selected.labels)}
                {selected.impact_score != null &&
                  ` · Impact: ${selected.impact_score >= 0 ? '+' : ''}${Number(selected.impact_score).toFixed(2)}`}
              </p>
            </div>
            <button onClick={() => setSelected(null)}
              className="w-7 h-7 rounded-lg flex items-center justify-center bg-white border border-slate-200 text-slate-400 hover:bg-slate-50">
              <X size={13} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Legend ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-1">
        {sortedTypes.map(([type]) => (
          <div key={type} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: NODE_COLORS[type] ?? NODE_COLORS.Default }} />
            <span className="text-[10px] text-slate-500">{NODE_LABELS[type] ?? type}</span>
          </div>
        ))}
      </div>

    </div>
  );
}
