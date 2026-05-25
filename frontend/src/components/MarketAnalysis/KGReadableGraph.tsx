/**
 * KGReadableGraph — 2D Knowledge Graph, lisible et aéré.
 *
 * Technique identique au WorldModel/GraphViewer :
 *  - nodeCanvasObjectMode 'replace'  → rendu nœud entièrement custom
 *  - linkCanvasObjectMode 'after'    → label relation dessiné AU-DESSUS du lien par défaut
 *  - linkCurvature 0.2               → arêtes courbes (arêtes parallèles séparées)
 *  - Forces D3 custom                → répulsion forte + collision + distance longue
 */
import {
  useRef, useCallback, useEffect, useState, useMemo, lazy, Suspense,
} from 'react';
import * as d3 from 'd3';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Maximize2, Filter, GitBranch, ZoomIn, ZoomOut, X,
} from 'lucide-react';
import type { KGSnapshot, KGStats } from '../../api/marketAnalysisApi';

const ForceGraph2D = lazy(() => import('react-force-graph-2d'));

// ── Couleurs nœuds ────────────────────────────────────────────────────────────

const NODE_CFG: Record<string, { color: string; emoji: string; label: string; r: number }> = {
  Company:        { color: '#0284C7', emoji: '🏢', label: 'Entreprise',    r: 26 },
  Competitor:     { color: '#DC2626', emoji: '⚔️',  label: 'Concurrent',    r: 24 },
  Technology:     { color: '#7C3AED', emoji: '⚙️',  label: 'Technologie',   r: 22 },
  Regulation:     { color: '#C2410C', emoji: '📜', label: 'Réglementation', r: 20 },
  MarketTrend:    { color: '#D97706', emoji: '📈', label: 'Tendance',       r: 20 },
  Sector:         { color: '#0F766E', emoji: '🏭', label: 'Secteur',        r: 20 },
  Country:        { color: '#15803D', emoji: '🌍', label: 'Pays',           r: 20 },
  Event:          { color: '#B45309', emoji: '⚡', label: 'Événement',      r: 18 },
  MacroIndicator: { color: '#6D28D9', emoji: '📊', label: 'Macro',          r: 18 },
  Person:         { color: '#BE185D', emoji: '👤', label: 'Personne',       r: 16 },
  News:           { color: '#475569', emoji: '📰', label: 'Actu',           r: 14 },
  Default:        { color: '#64748B', emoji: '◉',  label: 'Autre',          r: 16 },
};

const ALL_TYPES = Object.keys(NODE_CFG).filter(k => k !== 'Default' && k !== 'News');

// ── Disposition en couches (Sankey-like) ──────────────────────────────────────
// 0 = Sources (causes)  ·  1 = Médiateurs (propagation)  ·  2 = Cibles (impacts)
const LAYER: Record<string, 0 | 1 | 2> = {
  // Sources : événements, régulations, indicateurs déclencheurs
  Event:          0,
  Regulation:     0,
  MarketTrend:    0,
  MacroIndicator: 0,
  Person:         0,
  News:           0,
  // Médiateurs : entités qui propagent l'impact
  Sector:         1,
  Technology:     1,
  Country:        1,
  // Cibles : entités finales qui subissent l'impact
  Company:        2,
  Competitor:     2,
};
const layerOf = (label: string) => LAYER[label] ?? 1;

const LAYER_META = [
  { idx: 0, title: 'Sources',     subtitle: 'Causes',       icon: '⚡', color: '#B45309' },
  { idx: 1, title: 'Médiateurs',  subtitle: 'Propagation',  icon: '🔗', color: '#0F766E' },
  { idx: 2, title: 'Cibles',      subtitle: 'Impacts',      icon: '🎯', color: '#0284C7' },
] as const;

// Couleurs des types de relations
const REL_COLOR: Record<string, string> = {
  CAUSES_IMPACT_ON:   '#DC2626',
  IMPACTS:            '#EA580C',
  INFLUENCES:         '#D97706',
  ACQUIRED:           '#7C3AED',
  COMPETES_WITH:      '#EF4444',
  LAUNCHED:           '#059669',
  RECRUITS_IN:        '#0284C7',
  BELONGS_TO_SECTOR:  '#0F766E',
  SUPPLY_CHAIN_LINK:  '#EC4899',
  OPERATES_IN:        '#64748B',
  TRIGGERS_EVENT:     '#B91C1C',
  AFFECTS_INDICATOR:  '#4338CA',
  MENTIONS:           '#94A3B8',
};

function relColor(type: string) { return REL_COLOR[type] ?? '#94A3B8'; }

// ── Types internes ─────────────────────────────────────────────────────────────

interface GNode {
  id: string; name: string; label: string; ticker?: string;
  color: string; r: number; emoji: string; typeLabel: string;
  val: number;
  x?: number; y?: number;
}
interface GLink {
  source: string | GNode; target: string | GNode;
  type: string; impact_score?: number | null;
  color: string; width: number;
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  snapshot:        KGSnapshot | undefined;
  stats?:          KGStats;
  loading:         boolean;
  centerCompany:   string;
  onCompanyChange: (name: string) => void;
}

// ── Helpers canvas ────────────────────────────────────────────────────────────

function paintNode(
  node: any,
  ctx: CanvasRenderingContext2D,
  _gs: number,
  highlighted: Set<string>,
  hoveredId: string | null,
  centerName: string,
) {
  const n = node as GNode;
  const { x = 0, y = 0 } = n;
  const isCenter     = n.name === centerName;
  const isHighlight  = highlighted.size > 0 && highlighted.has(n.id);
  const isHover      = n.id === hoveredId;
  const isDimmed     = highlighted.size > 0 && !highlighted.has(n.id);
  const isActive     = isHighlight || isHover || isCenter;

  const alpha = isDimmed ? 0.12 : 1;
  const r = isCenter ? n.r + 6 : n.r;

  ctx.save();
  ctx.globalAlpha = alpha;

  // Glow externe pour nœuds actifs
  if (isActive) {
    const glow = ctx.createRadialGradient(x, y, r * 0.5, x, y, r + 14);
    glow.addColorStop(0, `${n.color}60`);
    glow.addColorStop(1, `${n.color}00`);
    ctx.beginPath();
    ctx.arc(x, y, r + 14, 0, 2 * Math.PI);
    ctx.fillStyle = glow;
    ctx.fill();
  }

  // Anneau extérieur
  ctx.beginPath();
  ctx.arc(x, y, r + 2, 0, 2 * Math.PI);
  ctx.fillStyle = isActive ? n.color : `${n.color}55`;
  ctx.fill();

  // Cercle principal avec gradient radial
  const grad = ctx.createRadialGradient(x - r * 0.28, y - r * 0.28, r * 0.1, x, y, r);
  grad.addColorStop(0, `${n.color}ff`);
  grad.addColorStop(0.55, `${n.color}dd`);
  grad.addColorStop(1, `${n.color}88`);
  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.fillStyle = grad;
  ctx.fill();

  // Emoji icône centré
  ctx.font = `${Math.round(r * 0.95)}px serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(n.emoji, x, y + 1);

  // ── Nom de l'entité en dessous ──────────────────────────────────────────────
  const nameStr = n.name.length > 24 ? n.name.slice(0, 22) + '…' : n.name;
  const nameFontSize = isCenter ? 12 : Math.max(9, Math.min(11, r * 0.42));
  ctx.font = `${isActive ? '700' : '600'} ${nameFontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  const nw = ctx.measureText(nameStr).width;
  const nh = nameFontSize + 2;
  const nx = x - nw / 2 - 5;
  const ny = y + r + 5;

  // Fond blanc arrondi
  ctx.fillStyle = 'rgba(255,255,255,0.93)';
  ctx.beginPath();
  (ctx as any).roundRect(nx, ny, nw + 10, nh, 4);
  ctx.fill();

  // Ombre portée légère
  ctx.fillStyle = 'rgba(0,0,0,0.08)';
  ctx.fillText(nameStr, x + 0.5, ny + 1.5);
  // Texte principal
  ctx.fillStyle = '#0F172A';
  ctx.fillText(nameStr, x, ny + 1);

  // ── Badge type (plus petit, sous le nom) ───────────────────────────────────
  const typeStr = n.typeLabel;
  const tfSize = nameFontSize - 1.5;
  ctx.font = `500 ${tfSize}px Inter, system-ui, sans-serif`;
  const tw = ctx.measureText(typeStr).width;
  const tx = x - tw / 2 - 4;
  const ty = ny + nh + 2;

  ctx.fillStyle = `${n.color}20`;
  ctx.beginPath();
  (ctx as any).roundRect(tx, ty, tw + 8, tfSize + 3, 3);
  ctx.fill();

  ctx.fillStyle = n.color;
  ctx.textBaseline = 'top';
  ctx.fillText(typeStr, x, ty + 1.5);

  // Ticker si présent
  if (n.ticker) {
    ctx.font = `500 ${tfSize - 1}px monospace`;
    ctx.fillStyle = '#059669';
    ctx.fillText(n.ticker, x, ty + tfSize + 5);
  }

  ctx.restore();
}

function paintLinkLabel(link: any, ctx: CanvasRenderingContext2D) {
  const src = link.source as GNode;
  const tgt = link.target as GNode;
  if (!src?.x || !tgt?.x) return;

  const dx = tgt.x - src.x;
  const dy = tgt.y - src.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 2) return;

  // Milieu de la courbe (curvature = 0.2 dans linkCurvature)
  const curvature = 0.2;
  const mx = (src.x + tgt.x) / 2 - curvature * dy * 0.5;
  const my = (src.y + tgt.y) / 2 + curvature * dx * 0.5;

  const relLabel = (link.type ?? '').replace(/_/g, ' ');
  const color = link.color as string;
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);

  const fontSize = 9;
  ctx.save();
  ctx.font = `700 ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const tw = ctx.measureText(relLabel).width;
  const pw = tw + 10;
  const ph = fontSize + 5;

  // Orienter le label dans la direction de la flèche
  const angle = Math.atan2(dy, dx);
  const flip  = angle > Math.PI / 2 || angle < -Math.PI / 2;

  ctx.translate(mx, my);
  ctx.rotate(flip ? angle + Math.PI : angle);

  // Fond pill blanc + bordure colorée
  ctx.fillStyle = 'rgba(255,255,255,0.96)';
  ctx.strokeStyle = `rgba(${r},${g},${b},0.45)`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  (ctx as any).roundRect(-pw / 2, -ph / 2, pw, ph, 5);
  ctx.fill();
  ctx.stroke();

  // Texte coloré
  ctx.fillStyle = `rgb(${r},${g},${b})`;
  ctx.fillText(relLabel, 0, 0);

  ctx.restore();
}

// ── Composant principal ───────────────────────────────────────────────────────

export default function KGReadableGraph({
  snapshot, stats, loading, centerCompany, onCompanyChange,
}: Props) {
  const fgRef       = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 900, height: 640 });

  const [typeFilter,  setTypeFilter]  = useState<string | null>(null);
  const [searchVal,   setSearchVal]   = useState('');
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set());
  const [hoveredId,   setHoveredId]   = useState<string | null>(null);
  const [selected,    setSelected]    = useState<GNode | null>(null);

  // ── Resize observer ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // ── Données graph ──────────────────────────────────────────────────────────
  const rawNodes = snapshot?.nodes ?? [];
  const rawEdges = snapshot?.edges ?? [];

  const degreeMap = useMemo(() => {
    const m: Record<string, number> = {};
    for (const e of rawEdges) { m[e.from] = (m[e.from] ?? 0) + 1; m[e.to] = (m[e.to] ?? 0) + 1; }
    return m;
  }, [rawEdges]);

  const nodes: GNode[] = useMemo(() => rawNodes
    .filter(n => !typeFilter || (n.labels ?? [])[0] === typeFilter)
    .map(n => {
      const label   = (n.labels ?? ['Company'])[0];
      const cfg     = NODE_CFG[label] ?? NODE_CFG.Default;
      const degree  = degreeMap[n.id] ?? 0;
      const isCenter = n.name === centerCompany;
      const rBoost  = Math.min(Math.floor(degree / 3), 6);
      const baseR   = isCenter ? cfg.r + 8 : cfg.r + rBoost;
      return {
        id: n.id, name: n.name, label, ticker: n.ticker,
        color: cfg.color, r: baseR, emoji: cfg.emoji, typeLabel: cfg.label,
        val: baseR * baseR,
      };
    }), [rawNodes, degreeMap, typeFilter, centerCompany]);

  const nodeIds = useMemo(() => new Set(nodes.map(n => n.id)), [nodes]);

  const links: GLink[] = useMemo(() => rawEdges
    .filter(e => nodeIds.has(e.from) && nodeIds.has(e.to))
    .map(e => ({
      source: e.from, target: e.to, type: e.type,
      impact_score: e.impact_score,
      color: relColor(e.type),
      width: Math.max(1.2, Math.min(4, Math.abs(e.impact_score ?? 0.2) * 4 + 1.2)),
    })), [rawEdges, nodeIds]);

  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  // ── D3 forces : layout en colonnes par couche (Sankey-like) ────────────────
  // On capture la ref une fois, puis on (ré)applique les forces dans un effet
  // qui réagit aux dimensions du canvas — sinon les colonnes ne s'ajusteraient
  // pas au resize.
  const handleRef = useCallback((fg: any) => {
    if (!fg) return;
    fgRef.current = fg;
  }, []);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const sim = fg.d3Force;
    if (!sim) return;

    const W = dimensions.width;
    const H = dimensions.height;
    // Centre X de chaque colonne (15% / 50% / 85% de la largeur)
    const colX: [number, number, number] = [W * 0.15, W * 0.50, W * 0.85];

    const getR = (n: any) => {
      const cfg = NODE_CFG[n.label] ?? NODE_CFG.Default;
      const degree = degreeMap[n.id] ?? 0;
      return cfg.r + Math.min(Math.floor(degree / 3), 6);
    };

    // Force horizontale FORTE : chaque nœud est attiré vers sa colonne
    sim('x',
      d3.forceX().x((n: any) => colX[layerOf(n.label)]).strength(0.85),
    );
    // Force verticale douce : étale les nœuds dans la hauteur
    sim('y',
      d3.forceY(H / 2).strength(0.06),
    );

    // Plus de force centrale (remplacée par forceX/forceY)
    sim('center')?.strength(0);

    // Répulsion forte — sépare les nœuds proches dans la même colonne
    sim('charge')
      ?.strength((n: any) => -(getR(n) ** 2) * 14)
      .distanceMax(600);

    // Liens : distance courte verticalement, longue horizontalement (entre colonnes)
    sim('link')
      ?.distance((l: any) => {
        const s: any = l.source;
        const t: any = l.target;
        const sameLayer = layerOf(s.label) === layerOf(t.label);
        const maxR = Math.max(getR(s), getR(t));
        return sameLayer ? maxR * 4 + 50 : maxR * 6 + 80;
      })
      // Strength faible pour que les liens ne ramènent pas les colonnes ensemble
      .strength(0.12);

    // Collision — gros padding pour ne pas tasser les nœuds
    sim('collision',
      d3.forceCollide()
        .radius((n: any) => getR(n) + 60)
        .strength(0.95),
    );

    fg.d3ReheatSimulation?.();
  }, [dimensions, degreeMap]);

  // ── Fit initial — padding généreux pour que la vue soit aérée ──────────────
  useEffect(() => {
    if (!nodes.length) return;
    const t = setTimeout(() => fgRef.current?.zoomToFit(900, 160), 1400);
    return () => clearTimeout(t);
  }, [nodes.length]);

  // ── Click nœud ────────────────────────────────────────────────────────────
  const handleNodeClick = useCallback((node: any) => {
    const n = node as GNode;
    setSelected(n);
    const ids = new Set<string>([n.id]);
    for (const l of links) {
      const s = typeof l.source === 'object' ? (l.source as GNode).id : l.source as string;
      const t = typeof l.target === 'object' ? (l.target as GNode).id : l.target as string;
      if (s === n.id) ids.add(t);
      if (t === n.id) ids.add(s);
    }
    setHighlighted(ids);
    if (fgRef.current && n.x != null && n.y != null) {
      fgRef.current.centerAt(n.x, n.y, 600);
      fgRef.current.zoom(2.8, 600);
    }
  }, [links]);

  const handleBgClick = useCallback(() => {
    setSelected(null);
    setHighlighted(new Set());
  }, []);

  // ── Callbacks canvas ───────────────────────────────────────────────────────
  const isHighlightActive = highlighted.size > 0;

  const paintNodeCb = useCallback((node: any, ctx: CanvasRenderingContext2D, gs: number) => {
    paintNode(node, ctx, gs, highlighted, hoveredId, centerCompany);
  }, [highlighted, hoveredId, centerCompany]);

  const paintLinkCb = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    // Dimmer les relations non-actives quand une sélection est active
    const src = typeof link.source === 'object' ? (link.source as GNode).id : link.source;
    const tgt = typeof link.target === 'object' ? (link.target as GNode).id : link.target;
    const dim = isHighlightActive && !(highlighted.has(src) && highlighted.has(tgt));
    if (dim) return; // on cache les labels des liens non-pertinents
    paintLinkLabel(link, ctx);
  }, [highlighted, isHighlightActive]);

  // Couleur du lien (dimme les non-actifs)
  const getLinkColor = useCallback((link: any) => {
    const src = typeof link.source === 'object' ? (link.source as GNode).id : link.source;
    const tgt = typeof link.target === 'object' ? (link.target as GNode).id : link.target;
    if (isHighlightActive && !(highlighted.has(src) && highlighted.has(tgt))) {
      return 'rgba(148,163,184,0.08)';
    }
    return link.color;
  }, [highlighted, isHighlightActive]);

  const getLinkWidth = useCallback((link: any) => {
    const src = typeof link.source === 'object' ? (link.source as GNode).id : link.source;
    const tgt = typeof link.target === 'object' ? (link.target as GNode).id : link.target;
    if (isHighlightActive && !(highlighted.has(src) && highlighted.has(tgt))) return 0.3;
    return link.width;
  }, [highlighted, isHighlightActive]);

  // ── Recherche ──────────────────────────────────────────────────────────────
  const handleSearch = useCallback(() => {
    const q = searchVal.trim().toLowerCase();
    if (!q) return;
    const found = nodes.find(n => n.name.toLowerCase().includes(q));
    if (found) {
      handleNodeClick(found);
    } else {
      onCompanyChange(searchVal.trim());
    }
    setSearchVal('');
  }, [searchVal, nodes, handleNodeClick, onCompanyChange]);

  // ── Sidebar — relations du nœud sélectionné ────────────────────────────────
  const selectedLinks = useMemo(() => {
    if (!selected) return [];
    return links.filter(l => {
      const s = typeof l.source === 'object' ? (l.source as GNode).id : l.source;
      const t = typeof l.target === 'object' ? (l.target as GNode).id : l.target;
      return s === selected.id || t === selected.id;
    });
  }, [selected, links]);

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-2xl"
        style={{ height: 640, background: '#F8FAFC', border: '1px solid rgba(148,163,184,0.2)' }}>
        <div className="flex flex-col items-center gap-3">
          <div className="relative w-12 h-12">
            <div className="absolute inset-0 rounded-full border-2 border-sky-400/40 animate-ping" />
            <div className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(2,132,199,0.08)' }}>
              <GitBranch size={22} style={{ color: '#0284C7' }} />
            </div>
          </div>
          <p className="text-sm font-medium text-sky-600">Chargement du graphe…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">

      {/* ── Barre de contrôles ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">

        {/* Recherche */}
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl flex-1 min-w-[220px]"
          style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.25)' }}>
          <Search size={13} className="text-slate-400 flex-shrink-0" />
          <input
            value={searchVal}
            onChange={e => setSearchVal(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder={`Rechercher… (centré : ${centerCompany})`}
            className="bg-transparent outline-none text-sm w-full"
            style={{ color: '#1E293B' }}
          />
        </div>

        {/* Filtres type */}
        <div className="flex items-center gap-1 flex-wrap">
          {[null, ...ALL_TYPES.slice(0, 6)].map(t => {
            const cfg    = t ? NODE_CFG[t] : null;
            const active = typeFilter === t;
            return (
              <button key={t ?? 'all'} onClick={() => setTypeFilter(active ? null : t)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-[10px] font-semibold transition-all"
                style={{
                  background: active ? `${cfg?.color ?? '#0284C7'}18` : 'rgba(255,255,255,0.85)',
                  color: active ? (cfg?.color ?? '#0284C7') : '#64748B',
                  border: `1px solid ${active ? (cfg?.color ?? '#0284C7') + '50' : 'rgba(148,163,184,0.25)'}`,
                }}>
                {t
                  ? <><span className="w-2 h-2 rounded-full" style={{ background: cfg?.color }} />{cfg?.label}</>
                  : <><Filter size={9} /> Tous</>}
              </button>
            );
          })}
        </div>

        {/* Zoom */}
        {([
          ['Zoom +',    () => fgRef.current?.zoom(1.4, 300),     <ZoomIn size={13} />],
          ['Zoom -',    () => fgRef.current?.zoom(0.7, 300),     <ZoomOut size={13} />],
          ['Ajuster',   () => fgRef.current?.zoomToFit(700, 80), <Maximize2 size={13} />],
        ] as const).map(([tip, action, icon]) => (
          <button key={tip as string} onClick={action as () => void} title={tip as string}
            className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(255,255,255,0.9)', color: '#64748B', border: '1px solid rgba(148,163,184,0.25)' }}>
            {icon}
          </button>
        ))}

        {/* Compteurs */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-mono"
          style={{ background: 'rgba(255,255,255,0.9)', border: '1px solid rgba(148,163,184,0.2)', color: '#64748B' }}>
          <span style={{ color: '#0284C7' }}>{nodes.length}</span> nœuds
          <span className="text-slate-300">·</span>
          <span style={{ color: '#7C3AED' }}>{links.length}</span> relations
        </div>
      </div>

      {/* ── Graphe + sidebar ──────────────────────────────────────────────── */}
      <div className="flex gap-3">

        {/* Canvas */}
        <div ref={containerRef} className="flex-1 rounded-2xl overflow-hidden relative"
          style={{ height: 640, background: '#F8FAFC', border: '1px solid rgba(148,163,184,0.2)' }}>

          {/* ── En-têtes de colonnes (Sankey) ──────────────────────────────── */}
          {nodes.length > 0 && (
            <>
              <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none px-4 pt-3">
                <div className="relative h-9">
                  {LAYER_META.map((l) => (
                    <div
                      key={l.idx}
                      className="absolute -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-full"
                      style={{
                        left:       `${[15, 50, 85][l.idx]}%`,
                        background: 'rgba(255,255,255,0.95)',
                        border:     `1px solid ${l.color}40`,
                        boxShadow:  '0 1px 6px rgba(0,0,0,0.04)',
                      }}
                    >
                      <span className="text-sm">{l.icon}</span>
                      <span
                        className="text-[11px] font-bold uppercase tracking-wide"
                        style={{ color: l.color }}
                      >
                        {l.title}
                      </span>
                      <span className="text-[10px] font-medium" style={{ color: l.color + 'AA' }}>
                        · {l.subtitle}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Séparateurs verticaux discrets entre colonnes (à 32.5% et 67.5%) */}
              <div className="absolute top-0 bottom-0 z-0 pointer-events-none"
                style={{ left: '32.5%', width: 1, background: 'linear-gradient(180deg, transparent 0%, rgba(148,163,184,0.12) 20%, rgba(148,163,184,0.12) 80%, transparent 100%)' }} />
              <div className="absolute top-0 bottom-0 z-0 pointer-events-none"
                style={{ left: '67.5%', width: 1, background: 'linear-gradient(180deg, transparent 0%, rgba(148,163,184,0.12) 20%, rgba(148,163,184,0.12) 80%, transparent 100%)' }} />
            </>
          )}

          {nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <GitBranch size={36} className="text-slate-300" />
              <p className="text-sm font-semibold text-slate-400">Knowledge Graph vide</p>
              <p className="text-xs text-slate-300">Lancez un cycle d'analyse pour peupler le graphe</p>
            </div>
          ) : (
            <Suspense fallback={
              <div className="flex items-center justify-center h-full">
                <p className="text-sm text-sky-400 animate-pulse">Initialisation du graphe…</p>
              </div>
            }>
              <ForceGraph2D
                ref={handleRef as any}
                graphData={graphData}
                width={dimensions.width}
                height={dimensions.height}
                backgroundColor="#F8FAFC"
                // ── Nœuds ──────────────────────────────────────────────────
                nodeCanvasObject={paintNodeCb}
                nodeCanvasObjectMode={() => 'replace'}
                nodeVal={(n: any) => n.val}
                nodeLabel=""
                // ── Liens (défaut) ─────────────────────────────────────────
                linkColor={getLinkColor}
                linkWidth={getLinkWidth}
                linkCurvature={0.2}
                linkDirectionalArrowLength={6}
                linkDirectionalArrowRelPos={1}
                linkDirectionalArrowColor={getLinkColor}
                linkDirectionalParticles={(l: any) => {
                  const s = typeof l.source === 'object' ? (l.source as GNode).id : l.source;
                  const t = typeof l.target === 'object' ? (l.target as GNode).id : l.target;
                  return (highlighted.has(s) && highlighted.has(t)) ? 3 : 0;
                }}
                linkDirectionalParticleWidth={2}
                linkDirectionalParticleColor={getLinkColor}
                // ── Label relation (au-dessus du lien) ──────────────────────
                linkCanvasObject={paintLinkCb}
                linkCanvasObjectMode={() => 'after'}
                // ── Physique ───────────────────────────────────────────────
                d3AlphaDecay={0.018}
                d3VelocityDecay={0.38}
                warmupTicks={80}
                cooldownTicks={150}
                // ── Interaction ────────────────────────────────────────────
                onNodeClick={handleNodeClick}
                onNodeHover={(n: any) => setHoveredId(n ? (n as GNode).id : null)}
                onBackgroundClick={handleBgClick}
              />
            </Suspense>
          )}

          {/* Hint */}
          <div className="absolute bottom-3 left-3 z-10 px-3 py-1.5 rounded-xl text-[10px] text-slate-400"
            style={{ background: 'rgba(255,255,255,0.88)', border: '1px solid rgba(148,163,184,0.2)' }}>
            Lecture : <span className="font-semibold text-slate-600">gauche → droite</span>
            <span className="mx-1.5">·</span>
            Clic nœud = voisins
            <span className="mx-1.5">·</span>
            Scroll = zoom
            <span className="mx-1.5">·</span>
            Drag = déplacer
          </div>
        </div>

        {/* Sidebar droite */}
        <div className="w-56 flex-shrink-0 flex flex-col gap-3 overflow-y-auto" style={{ maxHeight: 640 }}>

          {/* Nœud sélectionné */}
          <AnimatePresence>
            {selected && (
              <motion.div key={selected.id}
                initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 12 }}
                className="rounded-2xl overflow-hidden flex-shrink-0"
                style={{ background: 'rgba(255,255,255,0.97)', border: `1px solid ${selected.color}40`, boxShadow: '0 4px 18px rgba(0,0,0,0.09)' }}>
                <div className="flex items-center gap-2.5 p-3"
                  style={{ borderBottom: `1px solid ${selected.color}20` }}>
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-base flex-shrink-0"
                    style={{ background: `${selected.color}18` }}>
                    {selected.emoji}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: '#1E293B' }}>{selected.name}</p>
                    <p className="text-xs font-medium" style={{ color: selected.color }}>{selected.typeLabel}</p>
                  </div>
                  <button onClick={() => { setSelected(null); setHighlighted(new Set()); }}
                    className="p-1 rounded-lg text-slate-400 hover:text-slate-700">
                    <X size={11} />
                  </button>
                </div>

                <div className="p-3">
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
                    Relations ({selectedLinks.length})
                  </p>
                  <div className="space-y-1.5 max-h-64 overflow-y-auto">
                    {selectedLinks.slice(0, 15).map((l, i) => {
                      const srcId = typeof l.source === 'object' ? (l.source as GNode).id : l.source as string;
                      const tgtId = typeof l.target === 'object' ? (l.target as GNode).id : l.target as string;
                      const isFrom = srcId === selected.id;
                      const otherId = isFrom ? tgtId : srcId;
                      const other = nodes.find(n => n.id === otherId);
                      const sc = l.impact_score;
                      const scColor = sc == null ? '#64748B' : sc < 0 ? '#DC2626' : '#059669';
                      return (
                        <div key={i} className="rounded-xl px-2 py-1.5 space-y-0.5"
                          style={{ background: `${l.color}0D`, border: `1px solid ${l.color}20` }}>
                          {/* Direction */}
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400">{isFrom ? '→' : '←'}</span>
                            <span className="text-xs font-medium text-slate-700 truncate" title={other?.name}>
                              {other?.name ?? otherId}
                            </span>
                          </div>
                          {/* Type de relation */}
                          <div className="flex items-center justify-between">
                            <span className="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wide"
                              style={{ background: `${l.color}18`, color: l.color }}>
                              {(l.type ?? '').replace(/_/g, ' ')}
                            </span>
                            {sc != null && (
                              <span className="text-[10px] font-mono font-bold" style={{ color: scColor }}>
                                {sc >= 0 ? '+' : ''}{sc.toFixed(2)}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {selectedLinks.length > 15 && (
                    <p className="text-[10px] text-slate-400 mt-1.5 text-center">
                      +{selectedLinks.length - 15} autres…
                    </p>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Légende nœuds — groupée par couche (Sankey) */}
          <div className="rounded-2xl p-3 flex-shrink-0"
            style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.2)' }}>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
              Types de nœuds
            </p>
            <div className="space-y-2.5">
              {LAYER_META.map((layerMeta) => {
                const typesInLayer = ALL_TYPES.filter(t => layerOf(t) === layerMeta.idx);
                if (typesInLayer.length === 0) return null;
                return (
                  <div key={layerMeta.idx}>
                    <div className="flex items-center gap-1 mb-1">
                      <span className="text-[10px]">{layerMeta.icon}</span>
                      <p className="text-[9px] font-bold uppercase tracking-wider"
                        style={{ color: layerMeta.color }}>
                        {layerMeta.title}
                      </p>
                    </div>
                    <div className="space-y-1 pl-2">
                      {typesInLayer.map(t => {
                        const cfg = NODE_CFG[t];
                        const active = typeFilter === t;
                        return (
                          <button key={t} onClick={() => setTypeFilter(active ? null : t)}
                            className="flex items-center gap-2 w-full hover:opacity-80 transition-opacity">
                            <span className="text-sm">{cfg.emoji}</span>
                            <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: cfg.color }} />
                            <span className="text-[11px] font-medium" style={{ color: active ? cfg.color : '#64748B' }}>
                              {cfg.label}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Légende relations */}
          <div className="rounded-2xl p-3 flex-shrink-0"
            style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.2)' }}>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
              Types de relations
            </p>
            <div className="space-y-1.5">
              {Object.entries(REL_COLOR).filter(([k]) => k !== 'MENTIONS').map(([type, color]) => (
                <div key={type} className="flex items-center gap-2">
                  <div className="flex-shrink-0 h-0.5 w-5 rounded-full" style={{ background: color }} />
                  <span className="text-[10px] font-medium" style={{ color }}>
                    {type.replace(/_/g, ' ')}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Stats KG */}
          {stats && (
            <div className="rounded-2xl p-3 flex-shrink-0"
              style={{ background: 'rgba(255,255,255,0.95)', border: '1px solid rgba(148,163,184,0.2)' }}>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">Statistiques KG</p>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Nœuds</span>
                  <span className="font-mono font-semibold" style={{ color: '#0284C7' }}>{stats.total_nodes}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Relations</span>
                  <span className="font-mono font-semibold" style={{ color: '#7C3AED' }}>{stats.total_relations}</span>
                </div>
                {Object.entries(stats.nodes_by_label ?? {}).sort(([, a], [, b]) => b - a).slice(0, 6).map(([label, count]) => (
                  <div key={label} className="flex justify-between text-[11px]">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px]">{NODE_CFG[label]?.emoji ?? '◉'}</span>
                      <span className="text-slate-500">{label}</span>
                    </div>
                    <span className="font-mono text-slate-400">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
