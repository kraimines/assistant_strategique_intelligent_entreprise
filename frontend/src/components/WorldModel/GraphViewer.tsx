/**
 * GraphViewer.tsx — Force-directed graph with clear visual hierarchy.
 *
 * Hierarchy (size + importance):
 *   Department > Account/Customer > Manager/Employee > Project/Opportunity > Skill/Invoice/…
 *
 * Node size = base size (by label) × degree boost (more connections = bigger)
 * Colors: distinct per label, gradient fill, glow on hover
 */
import { useRef, useCallback, useEffect, useState, useMemo } from 'react';
import { useTheme } from '../../contexts/ThemeContext';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import * as d3 from 'd3';
import type { GraphNode, GraphLink } from '../../api/graphApi';
import { NODE_COLORS, NODE_ICONS, REL_COLORS } from './graphConfig';

// ── Importance hierarchy (base radius) ────────────────────────────────────────
const BASE_SIZE: Record<string, number> = {
  Company:      28,
  Department:   22,
  Account:      18,
  Customer:     17,
  Employee:     13,
  Project:      13,
  Opportunity:  12,
  Contact:      10,
  SalesOrder:    9,
  Supplier:     10,
  Skill:         7,
  Invoice:       8,
  Product:       7,
  Default:       8,
};

// ── Font sizes ────────────────────────────────────────────────────────────────
const LABEL_FONT: Record<string, number> = {
  Company:      13,
  Department:   11,
  Account:      10,
  Customer:     10,
  Employee:      9,
  Project:       9,
  Opportunity:   9,
  Default:       8,
};

interface Props {
  nodes: GraphNode[];
  links: GraphLink[];
  activeFilters: Set<string>;
  highlightId: string | null;
  onNodeClick: (node: GraphNode) => void;
  excludeLabels?: string[];
}

export default function GraphViewer({
  nodes, links, activeFilters, highlightId, onNodeClick, excludeLabels = [],
}: Props) {
  const fgRef = useRef<ForceGraphMethods>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const { theme } = useTheme();
  const graphBg = theme === 'light' ? '#f0f4f8' : '#0a0a0f';
  const labelTextColor = theme === 'light' ? 'rgba(30,30,30,0.85)' : 'rgba(255,255,255,0.80)';
  const labelShadow = theme === 'light' ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)';

  // ── Resize observer ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // ── Filter nodes ────────────────────────────────────────────────────────────
  const filteredNodes = useMemo(() => nodes.filter(n => {
    if (excludeLabels.includes(n.label)) return false;
    if (activeFilters.size > 0 && !activeFilters.has(n.label)) return false;
    return true;
  }), [nodes, excludeLabels, activeFilters]);

  const filteredNodeIds = useMemo(
    () => new Set(filteredNodes.map(n => n.id)),
    [filteredNodes],
  );

  const filteredLinks = useMemo(() => links.filter(l => {
    const s = typeof l.source === 'object' ? (l.source as any).id : l.source;
    const t = typeof l.target === 'object' ? (l.target as any).id : l.target;
    return filteredNodeIds.has(s) && filteredNodeIds.has(t);
  }), [links, filteredNodeIds]);

  // ── Degree map (connections count per node) ──────────────────────────────────
  const degreeMap = useMemo(() => {
    const map = new Map<string, number>();
    filteredLinks.forEach(l => {
      const s = typeof l.source === 'object' ? (l.source as any).id : l.source;
      const t = typeof l.target === 'object' ? (l.target as any).id : l.target;
      map.set(s, (map.get(s) ?? 0) + 1);
      map.set(t, (map.get(t) ?? 0) + 1);
    });
    return map;
  }, [filteredLinks]);

  // ── Compute radius for a node (base + degree boost) ─────────────────────────
  const getRadius = useCallback((node: GraphNode) => {
    const base = BASE_SIZE[node.label] ?? BASE_SIZE.Default;
    const degree = degreeMap.get(node.id) ?? 0;
    // +1 per 3 extra connections, capped at +6
    const boost = Math.min(Math.floor(degree / 3), 6);
    return base + boost;
  }, [degreeMap]);

  // ── nodeVal for physics (controls repulsion radius) ──────────────────────────
  const nodeVal = useCallback((node: any) => {
    const r = getRadius(node as GraphNode);
    return r * r;           // area-proportional mass
  }, [getRadius]);

  // ── Force engine customisation ───────────────────────────────────────────────
  const handleEngineStop = useCallback(() => {
    // nothing needed after warmup
  }, []);

  // Tune d3 forces once the graph mounts
  const handleRef = useCallback((fg: any) => {
    if (!fg) return;
    (fgRef as any).current = fg;
    const sim = fg.d3Force;
    if (!sim) return;

    // Strong repulsion so nodes don't overlap
    sim('charge')
      ?.strength((n: any) => -(getRadius(n as GraphNode) ** 2) * 8)
      .distanceMax(400);

    // Longer links for top-level nodes
    sim('link')
      ?.distance((l: any) => {
        const s: any = l.source;
        const t: any = l.target;
        const maxR = Math.max(
          getRadius(s as GraphNode),
          getRadius(t as GraphNode),
        );
        return maxR * 5 + 20;
      })
      .strength(0.4);

    // Gentle centering
    sim('center')?.strength(0.05);

    // Collision: prevent any overlap
    sim('collision', d3.forceCollide().radius((n: any) => getRadius(n as GraphNode) + 8).strength(0.9));
  }, [getRadius]);

  // ── Center on highlighted node ───────────────────────────────────────────────
  useEffect(() => {
    if (!highlightId || !fgRef.current) return;
    const node = filteredNodes.find(n => n.id === highlightId);
    if (node && (node as any).x != null) {
      fgRef.current.centerAt((node as any).x, (node as any).y, 600);
      fgRef.current.zoom(3.5, 600);
    }
  }, [highlightId, filteredNodes]);

  // ── Canvas node painter ──────────────────────────────────────────────────────
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const gn = node as GraphNode;
    const color = NODE_COLORS[gn.label] ?? NODE_COLORS.Default;
    const icon  = NODE_ICONS[gn.label]  ?? NODE_ICONS.Default;
    const r     = getRadius(gn);
    const x     = node.x ?? 0;
    const y     = node.y ?? 0;
    const isHighlighted = gn.id === highlightId;
    const isHovered     = gn.id === hoveredId;
    const isActive      = isHighlighted || isHovered;

    // ── Outer glow for active nodes ──
    if (isActive) {
      const glowR = r + 10;
      const glow = ctx.createRadialGradient(x, y, r * 0.5, x, y, glowR);
      glow.addColorStop(0, `${color}55`);
      glow.addColorStop(1, `${color}00`);
      ctx.beginPath();
      ctx.arc(x, y, glowR, 0, 2 * Math.PI);
      ctx.fillStyle = glow;
      ctx.fill();
    }

    // ── Ring border ──
    ctx.beginPath();
    ctx.arc(x, y, r + 1.5, 0, 2 * Math.PI);
    ctx.fillStyle = isActive ? color : `${color}66`;
    ctx.fill();

    // ── Main filled circle ──
    const grad = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r);
    grad.addColorStop(0, `${color}ff`);
    grad.addColorStop(0.6, `${color}cc`);
    grad.addColorStop(1, `${color}66`);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = grad;
    ctx.fill();

    // ── Emoji icon ──
    if (r >= 9) {
      ctx.font      = `${Math.round(r * 1.0)}px serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(icon, x, y);
    }

    // ── Label below node ──
    const fontSize = LABEL_FONT[gn.label] ?? LABEL_FONT.Default;
    const label    = gn.name ?? '';
    const maxChars = r >= 14 ? 20 : r >= 10 ? 14 : 10;
    const display  = label.length > maxChars ? label.slice(0, maxChars - 1) + '…' : label;

    ctx.font          = `${isActive ? 'bold ' : ''}${fontSize}px Inter, sans-serif`;
    ctx.textAlign     = 'center';
    ctx.textBaseline  = 'top';

    // Text shadow for readability
    ctx.fillStyle = labelShadow;
    ctx.fillText(display, x + 0.5, y + r + 3.5);
    ctx.fillStyle = isActive ? '#ffffff' : labelTextColor;
    ctx.fillText(display, x, y + r + 3);

    // ── Sub-label (role or status) for important nodes ──
    if (r >= 12 && gn.props) {
      const sub = (gn.props.role ?? gn.props.status ?? gn.props.stage ?? gn.props.industry) as string | undefined;
      if (sub) {
        const subDisplay = String(sub).length > 16 ? String(sub).slice(0, 15) + '…' : String(sub);
        ctx.font      = `${fontSize - 1}px Inter, sans-serif`;
        ctx.fillStyle = `${color}bb`;
        ctx.fillText(subDisplay, x, y + r + 3 + fontSize + 1);
      }
    }
  }, [highlightId, hoveredId, getRadius, labelShadow, labelTextColor]);

  // ── Link colour + width ──────────────────────────────────────────────────────
  const linkColor = useCallback((link: any) => {
    const src = typeof link.source === 'object' ? link.source : null;
    const tgt = typeof link.target === 'object' ? link.target : null;
    const isConnected = src?.id === highlightId || tgt?.id === highlightId
                      || src?.id === hoveredId   || tgt?.id === hoveredId;
    const base = REL_COLORS[(link as GraphLink).type] ?? REL_COLORS.Default;
    return isConnected ? base.replace(/[\d.]+\)$/, '0.9)') : base;
  }, [highlightId, hoveredId]);

  const linkWidth = useCallback((link: any) => {
    const src = typeof link.source === 'object' ? link.source : null;
    const tgt = typeof link.target === 'object' ? link.target : null;
    const isConnected = src?.id === highlightId || tgt?.id === highlightId
                      || src?.id === hoveredId   || tgt?.id === hoveredId;
    const thickTypes = ['HAS_OPPORTUNITY', 'MANAGES_PROJECT', 'HAS_DEPARTMENT', 'BELONGS_TO'];
    return isConnected ? 2.5 : thickTypes.includes((link as GraphLink).type) ? 1.5 : 0.8;
  }, [highlightId, hoveredId]);

  const linkDirectionalParticles = useCallback((link: any) => {
    const src = typeof link.source === 'object' ? link.source : null;
    const tgt = typeof link.target === 'object' ? link.target : null;
    return (src?.id === highlightId || tgt?.id === highlightId) ? 3 : 0;
  }, [highlightId]);

  // ── Empty state ──────────────────────────────────────────────────────────────
  if (filteredNodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <div className="text-4xl">🕸️</div>
        <p className="text-white/40 text-sm">Aucune donnée — vérifiez la connexion Neo4j</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full h-full relative">
      <ForceGraph2D
        ref={handleRef as any}
        graphData={{ nodes: filteredNodes as any[], links: filteredLinks as any[] }}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor={graphBg}
        // Node painting
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => 'replace'}
        nodeVal={nodeVal}
        // Links
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={linkColor}
        linkCurvature={0.12}
        linkDirectionalParticles={linkDirectionalParticles}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleColor={linkColor}
        // Physics
        d3AlphaDecay={0.025}
        d3VelocityDecay={0.4}
        warmupTicks={120}
        cooldownTicks={100}
        // Events
        onNodeClick={(node: any) => onNodeClick(node as GraphNode)}
        onNodeHover={(node: any) => setHoveredId(node ? (node as GraphNode).id : null)}
        onEngineStop={handleEngineStop}
        nodeLabel={() => ''}   // we draw our own labels
      />

      {/* Legend */}
      <div className="absolute bottom-4 right-4 flex flex-col gap-1.5 text-xs"
        style={{ background: 'var(--bg-overlay-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, padding: '10px 12px' }}>
        <p className="font-semibold uppercase tracking-widest text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>Taille = Importance</p>
        {[
          ['Department', '🏛️', 'Département'],
          ['Employee',   '👤', 'Employé'],
          ['Project',    '📁', 'Projet'],
          ['Skill',      '⚡', 'Compétence'],
        ].map(([label, icon, fr]) => (
          <div key={label} className="flex items-center gap-2">
            <div className="rounded-full flex-shrink-0 flex items-center justify-center text-[10px]"
              style={{
                width:  BASE_SIZE[label] * 1.2,
                height: BASE_SIZE[label] * 1.2,
                background: `${NODE_COLORS[label]}33`,
                border: `1px solid ${NODE_COLORS[label]}66`,
              }}>
              {icon}
            </div>
            <span className="text-white/50">{fr}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
