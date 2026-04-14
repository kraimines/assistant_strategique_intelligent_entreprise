/**
 * KGExplorer — Force-directed graph visualization of the Knowledge Graph.
 * Uses react-force-graph-2d (already in package.json).
 * Shows nodes colored by type, edges colored by impact_score, and a
 * side panel with KG stats + hidden risks.
 */
import { useRef, useCallback, useEffect, useState } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { motion, AnimatePresence } from 'framer-motion';
import { GitBranch, AlertTriangle, Search, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import type { KGSnapshot, KGStats, HiddenRisk } from '../../api/marketAnalysisApi';

interface Props {
  snapshot: KGSnapshot | undefined;
  stats: KGStats | undefined;
  hiddenRisks: HiddenRisk[];
  loading: boolean;
  centerCompany: string;
  onCompanyChange: (name: string) => void;
}

// ── Node color by label ────────────────────────────────────────────────────────
const NODE_COLORS: Record<string, string> = {
  Company:        '#00d4ff',
  Sector:         '#7c3aed',
  Country:        '#10b981',
  Event:          '#f59e0b',
  MacroIndicator: '#ec4899',
  News:           'rgba(255,255,255,0.35)',
  Default:        'rgba(255,255,255,0.4)',
};

// ── Edge color by impact_score ────────────────────────────────────────────────
function edgeColor(score?: number): string {
  if (score === undefined || score === null) return 'rgba(255,255,255,0.12)';
  if (score <= -0.5) return 'rgba(239,68,68,0.6)';
  if (score < 0)    return 'rgba(249,115,22,0.5)';
  if (score >= 0.5) return 'rgba(16,185,129,0.6)';
  if (score > 0)    return 'rgba(0,212,255,0.4)';
  return 'rgba(255,255,255,0.15)';
}

// ── Selected node popup ────────────────────────────────────────────────────────
interface NodeDetail {
  id: string;
  name: string;
  label: string;
  ticker?: string;
  edges: { type: string; target: string; score?: number; reason?: string }[];
}

export default function KGExplorer({
  snapshot, stats, hiddenRisks, loading, centerCompany, onCompanyChange,
}: Props) {
  const fgRef = useRef<ForceGraphMethods>(null!);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 600, h: 420 });
  const [selected, setSelected] = useState<NodeDetail | null>(null);
  const [searchVal, setSearchVal] = useState('');

  // Build graph data from snapshot
  const nodes = (snapshot?.nodes ?? []).map((n) => ({
    id: n.id,
    name: n.name,
    label: (n.labels ?? ['Company'])[0],
    ticker: n.ticker,
    val: n.name === centerCompany ? 5 : 2,
    color: NODE_COLORS[(n.labels ?? ['Company'])[0]] ?? NODE_COLORS.Default,
  }));

  const links = (snapshot?.edges ?? []).map((e, i) => ({
    id: `e${i}`,
    source: e.from,
    target: e.to,
    type: e.type,
    impact_score: e.impact_score,
    confidence: e.confidence,
    reason: e.reason,
    color: edgeColor(e.impact_score),
  }));

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setDims({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Center on Talan on load
  useEffect(() => {
    if (!fgRef.current || !nodes.length) return;
    setTimeout(() => {
      fgRef.current?.zoomToFit(400, 40);
    }, 500);
  }, [nodes.length]);

  const handleNodeClick = useCallback(
    (node: any) => {
      const nodeEdges = links
        .filter((l) => l.source === node.id || l.target === node.id)
        .slice(0, 8)
        .map((l) => {
          const targetId = l.source === node.id ? l.target : l.source;
          const targetNode = nodes.find((n) => n.id === targetId);
          return {
            type: l.type,
            target: targetNode?.name ?? targetId,
            score: l.impact_score,
            reason: l.reason,
          };
        });
      setSelected({
        id: node.id,
        name: node.name,
        label: node.label,
        ticker: node.ticker,
        edges: nodeEdges,
      });
    },
    [links, nodes]
  );

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isCenter = node.name === centerCompany;
      const isSelected = selected?.id === node.id;
      const r = isCenter ? 14 : isSelected ? 10 : 7;

      // Glow for center / selected
      if (isCenter || isSelected) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
        ctx.fillStyle = isCenter
          ? 'rgba(0,212,255,0.15)'
          : 'rgba(255,255,255,0.08)';
        ctx.fill();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = node.color;
      ctx.fill();

      // Label
      if (globalScale > 0.8 || isCenter) {
        const fontSize = isCenter ? 12 : 9;
        ctx.font = `${isCenter ? 'bold ' : ''}${fontSize / globalScale}px Sans-Serif`;
        ctx.fillStyle = isCenter ? '#ffffff' : 'rgba(255,255,255,0.7)';
        ctx.textAlign = 'center';
        ctx.fillText(node.name, node.x, node.y + r + 10 / globalScale);
      }
    },
    [centerCompany, selected]
  );

  const paintEdge = useCallback(
    (link: any, ctx: CanvasRenderingContext2D) => {
      const src = link.source as any;
      const tgt = link.target as any;
      if (!src?.x || !tgt?.x) return;
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = link.color;
      ctx.lineWidth = Math.abs(link.impact_score ?? 0.2) * 3 + 0.5;
      ctx.stroke();
    },
    []
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[480px] rounded-2xl bg-white/2 border border-white/6">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/15 flex items-center justify-center animate-pulse">
            <GitBranch size={20} className="text-violet-400" />
          </div>
          <p className="text-white/40 text-sm">Chargement du Knowledge Graph…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Top bar: search + company input + zoom controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl flex-1 min-w-[200px]"
          style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
          <Search size={13} className="text-white/30 flex-shrink-0" />
          <input
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && searchVal.trim()) { onCompanyChange(searchVal.trim()); setSearchVal(''); } }}
            placeholder={`Centre: ${centerCompany} — entrez un nom + Enter`}
            className="bg-transparent outline-none text-xs text-white/70 placeholder-white/25 w-full"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {[
            { icon: <ZoomIn size={14} />, action: () => fgRef.current?.zoom(1.5, 300) },
            { icon: <ZoomOut size={14} />, action: () => fgRef.current?.zoom(0.7, 300) },
            { icon: <Maximize2 size={14} />, action: () => fgRef.current?.zoomToFit(400, 40) },
          ].map(({ icon, action }, i) => (
            <button key={i} onClick={action}
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
              style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.45)' }}>
              {icon}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-4">
        {/* Graph canvas */}
        <div
          ref={containerRef}
          className="flex-1 rounded-2xl overflow-hidden relative"
          style={{
            background: 'radial-gradient(ellipse at center, rgba(124,58,237,0.04) 0%, rgba(10,10,15,0.8) 100%)',
            border: '1px solid rgba(255,255,255,0.07)',
            height: 480,
          }}
        >
          {nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <GitBranch size={40} className="text-white/10" />
              <p className="text-white/25 text-sm">Knowledge Graph vide</p>
              <p className="text-white/15 text-xs">Lancez un cycle pour peupler le graphe</p>
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef}
              width={dims.w}
              height={dims.h}
              graphData={{ nodes, links }}
              nodeCanvasObject={paintNode}
              nodeCanvasObjectMode={() => 'replace'}
              linkCanvasObject={paintEdge}
              linkCanvasObjectMode={() => 'replace'}
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => setSelected(null)}
              cooldownTicks={100}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
              backgroundColor="transparent"
            />
          )}
        </div>

        {/* Right column: node detail + legend + KG stats */}
        <div className="w-60 flex-shrink-0 flex flex-col gap-3">
          {/* Node detail */}
          <AnimatePresence>
            {selected && (
              <motion.div
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
                className="rounded-xl p-3 space-y-2.5"
                style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.10)' }}
              >
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ background: NODE_COLORS[selected.label] ?? NODE_COLORS.Default }} />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-white/85 truncate">{selected.name}</p>
                    <p className="text-[10px] text-white/35">{selected.label}{selected.ticker ? ` · ${selected.ticker}` : ''}</p>
                  </div>
                </div>
                {selected.edges.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] text-white/30">Relations</p>
                    {selected.edges.slice(0, 6).map((e, i) => {
                      const sc = e.score;
                      const col = sc != null ? (sc < 0 ? '#ef4444' : '#10b981') : 'rgba(255,255,255,0.3)';
                      return (
                        <div key={i} className="flex items-center gap-1.5 text-[10px]">
                          <span className="text-white/40 truncate flex-1">{e.target}</span>
                          {sc != null && (
                            <span className="font-mono flex-shrink-0" style={{ color: col }}>
                              {sc >= 0 ? '+' : ''}{sc.toFixed(2)}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Legend */}
          <div className="rounded-xl p-3"
            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
            <p className="text-[10px] text-white/30 mb-2">Légende des nœuds</p>
            <div className="space-y-1.5">
              {Object.entries(NODE_COLORS).filter(([k]) => k !== 'Default').map(([label, color]) => (
                <div key={label} className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                  <span className="text-[10px] text-white/50">{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* KG Stats */}
          {stats && (
            <div className="rounded-xl p-3 space-y-2"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <p className="text-[10px] text-white/30">Statistiques KG</p>
              <div className="space-y-1">
                <div className="flex justify-between text-[10px]">
                  <span className="text-white/40">Nœuds</span>
                  <span className="text-cyan-400 font-mono">{stats.total_nodes}</span>
                </div>
                <div className="flex justify-between text-[10px]">
                  <span className="text-white/40">Relations</span>
                  <span className="text-violet-400 font-mono">{stats.total_relations}</span>
                </div>
                {Object.entries(stats.nodes_by_label ?? {}).map(([label, count]) => (
                  <div key={label} className="flex justify-between text-[10px]">
                    <span className="text-white/30">{label}</span>
                    <span className="text-white/50 font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Hidden risks list */}
      {hiddenRisks.length > 0 && (
        <div className="rounded-xl p-4"
          style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.15)' }}>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-red-400" />
            <p className="text-sm font-semibold text-red-300">Risques Cachés Détectés</p>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400">{hiddenRisks.length}</span>
          </div>
          <div className="space-y-2">
            {hiddenRisks.slice(0, 5).map((r, i) => (
              <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg"
                style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div className="w-6 h-6 rounded-lg bg-red-500/15 flex items-center justify-center flex-shrink-0 text-[10px] text-red-400 font-bold">
                  {r.hops}↑
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-white/70">{r.source}</p>
                  <p className="text-[10px] text-white/35">{r.source_type} · score: <span className="text-red-400 font-mono">{r.chain_score?.toFixed(2)}</span></p>
                  {r.reasons?.[0] && (
                    <p className="text-[10px] text-white/30 mt-0.5 line-clamp-1">{r.reasons[0]}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
