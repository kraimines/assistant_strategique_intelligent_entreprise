/**
 * PropagationGraph — visual DAG of simulation propagation paths.
 *
 * Converts the list of PropagationPath objects into a force-directed graph
 * where:
 *   - nodes are coloured by entity type (same palette as KGReadableGraph)
 *   - edges are green (positive impact) or red (negative)
 *   - edge thickness = |impact_score|
 *   - "Talan" is highlighted with a gold ring
 *   - clicking a node shows its details in a side panel
 */
import { useRef, useCallback, useEffect, useMemo, lazy, Suspense, useState } from 'react';
import type { PropagationPath } from '../../api/marketAnalysisApi';

const ForceGraph2D = lazy(() => import('react-force-graph-2d'));

// ── Node palette (mirrors KGReadableGraph) ────────────────────────────────────

const NODE_CFG: Record<string, { color: string; emoji: string; r: number }> = {
  Company:         { color: '#0284C7', emoji: '🏢', r: 22 },
  Competitor:      { color: '#DC2626', emoji: '⚔️',  r: 20 },
  Sector:          { color: '#0F766E', emoji: '🏭', r: 18 },
  Country:         { color: '#15803D', emoji: '🌍', r: 18 },
  Event:           { color: '#B45309', emoji: '⚡', r: 16 },
  Regulation:      { color: '#C2410C', emoji: '📜', r: 18 },
  Technology:      { color: '#7C3AED', emoji: '⚙️',  r: 16 },
  MacroIndicator:  { color: '#6D28D9', emoji: '📊', r: 16 },
  BusinessUnit:    { color: '#0EA5E9', emoji: '🏦', r: 20 },
  Client:          { color: '#059669', emoji: '🤝', r: 16 },
  Supplier:        { color: '#D97706', emoji: '📦', r: 16 },
  Default:         { color: '#64748B', emoji: '◉',  r: 14 },
};

const cfgOf = (type?: string) => NODE_CFG[type ?? ''] ?? NODE_CFG.Default;

// ── Graph builder ─────────────────────────────────────────────────────────────

interface GNode { id: string; name: string; type: string; isSource?: boolean; isTalan?: boolean }
interface GEdge { source: string; target: string; impact: number; label: string }

function buildGraph(paths: PropagationPath[]): { nodes: GNode[]; edges: GEdge[] } {
  const nodeMap = new Map<string, GNode>();
  const edgeSet  = new Map<string, GEdge>();

  const addNode = (name: string, type: string, flags?: Partial<GNode>) => {
    if (!nodeMap.has(name)) nodeMap.set(name, { id: name, name, type, ...flags });
  };

  paths.forEach(path => {
    const chainNodes = [
      { name: path.source_name, type: path.source_type },
      ...(path.steps ?? []).map(s => ({ name: s.node_name, type: s.node_type })),
    ];

    chainNodes.forEach((n, i) => {
      addNode(n.name, n.type, {
        isSource: i === 0,
        isTalan:  n.name === 'Talan',
      });

      if (i > 0) {
        const prev = chainNodes[i - 1];
        const step = path.steps?.[i - 1];
        const key  = `${prev.name}→${n.name}`;
        if (!edgeSet.has(key)) {
          edgeSet.set(key, {
            source: prev.name,
            target: n.name,
            impact: step?.impact_score ?? 0,
            label:  step?.relation_type ?? 'CAUSES_IMPACT_ON',
          });
        }
      }
    });
  });

  return { nodes: [...nodeMap.values()], edges: [...edgeSet.values()] };
}

// ── Canvas node renderer ──────────────────────────────────────────────────────

function paintNode(node: any, ctx: CanvasRenderingContext2D, globalScale: number) {
  const cfg  = cfgOf(node.type);
  const r    = cfg.r / Math.max(1, globalScale * 0.4);
  const x    = node.x as number;
  const y    = node.y as number;
  const fs   = Math.max(8, 11 / globalScale);

  // Talan: gold outer ring
  if (node.isTalan) {
    ctx.beginPath();
    ctx.arc(x, y, r + 4, 0, 2 * Math.PI);
    ctx.fillStyle = '#FBBF24';
    ctx.fill();
  }

  // Source: dashed ring
  if (node.isSource && !node.isTalan) {
    ctx.beginPath();
    ctx.arc(x, y, r + 3, 0, 2 * Math.PI);
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = cfg.color;
    ctx.lineWidth   = 1.5;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Fill circle
  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.fillStyle   = node.__selected ? cfg.color : cfg.color + 'DD';
  ctx.shadowColor = cfg.color;
  ctx.shadowBlur  = node.__selected ? 12 : 4;
  ctx.fill();
  ctx.shadowBlur  = 0;

  // Emoji
  ctx.font          = `${Math.max(10, r * 0.8)}px serif`;
  ctx.textAlign     = 'center';
  ctx.textBaseline  = 'middle';
  ctx.fillStyle     = '#FFFFFF';
  ctx.fillText(cfg.emoji, x, y);

  // Label below
  ctx.font          = `bold ${fs}px Inter, sans-serif`;
  ctx.textAlign     = 'center';
  ctx.textBaseline  = 'top';
  ctx.fillStyle     = '#1E293B';
  ctx.strokeStyle   = 'rgba(255,255,255,0.85)';
  ctx.lineWidth     = 3;
  const label       = node.name.length > 20 ? node.name.slice(0, 18) + '…' : node.name;
  ctx.strokeText(label, x, y + r + 4);
  ctx.fillText(label, x, y + r + 4);
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  paths: PropagationPath[];
  height?: number;
}

export default function PropagationGraph({ paths, height = 340 }: Props) {
  const graphRef  = useRef<any>(null);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [dims, setDims] = useState({ w: 600, h: height });
  const containerRef = useRef<HTMLDivElement>(null);

  const { nodes, edges } = useMemo(() => buildGraph(paths), [paths]);

  // Responsive width
  useEffect(() => {
    const obs = new ResizeObserver(e => {
      const w = e[0]?.contentRect.width ?? 600;
      setDims({ w, h: height });
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [height]);

  // D3 forces
  const handleEngineStop = useCallback(() => {
    graphRef.current?.zoomToFit(400, 40);
  }, []);

  // Link color by impact
  const linkColor = useCallback((link: any) => {
    const imp = (link as GEdge).impact;
    if (imp > 0.1)  return '#16A34A';   // green — positive
    if (imp < -0.1) return '#DC2626';   // red — negative
    return '#94A3B8';
  }, []);

  const linkWidth = useCallback((link: any) =>
    Math.max(1, Math.abs((link as GEdge).impact) * 4), []);

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, gs: number) => {
    node.__selected = selected?.id === node.id;
    paintNode(node, ctx, gs);
  }, [selected]);

  const graphData = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n })),
    links: edges.map(e => ({
      source: e.source, target: e.target,
      impact: e.impact, label: e.label,
    })),
  }), [nodes, edges]);

  if (paths.length === 0) return null;

  return (
    <div style={{ fontFamily: 'Inter, sans-serif' }}>
      <div
        ref={containerRef}
        style={{
          width: '100%', height, borderRadius: 12, overflow: 'hidden',
          background: 'linear-gradient(135deg,#F0F9FF 0%,#F8FAFC 100%)',
          border: '1px solid var(--border-subtle)',
          position: 'relative',
        }}
      >
        <Suspense fallback={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 14 }}>
            Chargement du graphe…
          </div>
        }>
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={dims.w}
            height={dims.h}
            backgroundColor="transparent"
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => 'replace'}
            nodePointerAreaPaint={(node: any, color, ctx) => {
              const r = cfgOf(node.type).r + 4;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fill();
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkDirectionalArrowLength={6}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.15}
            linkDirectionalParticles={2}
            linkDirectionalParticleWidth={2}
            linkDirectionalParticleColor={linkColor}
            onNodeClick={(node: any) =>
              setSelected(prev => prev?.id === node.id ? null : node as GNode)
            }
            onEngineStop={handleEngineStop}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTime={2500}
          />
        </Suspense>

        {/* Legend */}
        <div style={{
          position: 'absolute', bottom: 10, left: 12,
          display: 'flex', gap: 12, flexWrap: 'wrap',
        }}>
          {[
            { color: '#16A34A', label: 'Impact positif' },
            { color: '#DC2626', label: 'Impact négatif' },
            { color: '#FBBF24', label: 'Talan (cible)' },
          ].map(l => (
            <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 12, height: 12, borderRadius: '50%', background: l.color }} />
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Selected node tooltip */}
      {selected && (
        <div style={{
          marginTop: 10,
          background: 'white', border: '1px solid var(--border-subtle)',
          borderRadius: 10, padding: '12px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: cfgOf(selected.type).color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, flexShrink: 0,
          }}>
            {cfgOf(selected.type).emoji}
          </div>
          <div>
            <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: 14 }}>
              {selected.name}
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {selected.type}
              {selected.isTalan && ' — Nœud cible de la simulation'}
              {selected.isSource && ' — Source de l\'événement'}
            </div>
          </div>
          <button
            onClick={() => setSelected(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: 18 }}
          >×</button>
        </div>
      )}
    </div>
  );
}
