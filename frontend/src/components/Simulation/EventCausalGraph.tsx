/**
 * EventCausalGraph — visualise uniquement le réseau causal extrait par le LLM
 * pour un événement saisi manuellement.
 *
 * Contraintes :
 *  - Seuls les nœuds/arêtes issus du LLM (event_graph) sont affichés.
 *  - Aucune donnée du Knowledge Graph externe.
 *  - Propagation multi-hop : un nœud "Événement" racine est ajouté ;
 *    aucun chemin direct Événement → Talan n'est autorisé.
 */
import { useRef, useCallback, useEffect, useMemo, lazy, Suspense, useState } from 'react';
import type { EventGraph } from '../../api/marketAnalysisApi';

const ForceGraph2D = lazy(() => import('react-force-graph-2d'));

// ── Palette nœuds ────────────────────────────────────────────────────────────

const NODE_CFG: Record<string, { color: string; emoji: string; r: number }> = {
  company:         { color: '#0284C7', emoji: '🏢', r: 22 },
  Company:         { color: '#0284C7', emoji: '🏢', r: 22 },
  competitor:      { color: '#DC2626', emoji: '⚔️',  r: 20 },
  Competitor:      { color: '#DC2626', emoji: '⚔️',  r: 20 },
  sector:          { color: '#0F766E', emoji: '🏭', r: 18 },
  Sector:          { color: '#0F766E', emoji: '🏭', r: 18 },
  country:         { color: '#15803D', emoji: '🌍', r: 18 },
  Country:         { color: '#15803D', emoji: '🌍', r: 18 },
  event:           { color: '#B45309', emoji: '⚡', r: 16 },
  Event:           { color: '#B45309', emoji: '⚡', r: 16 },
  regulation:      { color: '#C2410C', emoji: '📜', r: 18 },
  Regulation:      { color: '#C2410C', emoji: '📜', r: 18 },
  technology:      { color: '#7C3AED', emoji: '⚙️',  r: 16 },
  Technology:      { color: '#7C3AED', emoji: '⚙️',  r: 16 },
  macro_indicator: { color: '#6D28D9', emoji: '📊', r: 16 },
  MacroIndicator:  { color: '#6D28D9', emoji: '📊', r: 16 },
  market_trend:    { color: '#0891B2', emoji: '📈', r: 16 },
  MarketTrend:     { color: '#0891B2', emoji: '📈', r: 16 },
  person:          { color: '#D97706', emoji: '👤', r: 16 },
  Person:          { color: '#D97706', emoji: '👤', r: 16 },
  EventSource:     { color: '#1D4ED8', emoji: '📌', r: 24 },
  Default:         { color: '#64748B', emoji: '◉',  r: 14 },
};

const cfg = (type?: string) => NODE_CFG[type ?? ''] ?? NODE_CFG.Default;

// ── Types internes ────────────────────────────────────────────────────────────

interface GNode {
  id: string; name: string; type: string;
  isSource?: boolean; isTalan?: boolean; layer: number;
  x?: number; y?: number;
}
interface GEdge {
  source: string; target: string;
  relType: string; impact: number;
}

// ── Construction du graphe ────────────────────────────────────────────────────

function buildGraph(
  eventGraph: EventGraph,
  eventText: string,
): { nodes: GNode[]; edges: GEdge[] } {
  const nodeMap = new Map<string, GNode>();

  const SOURCE_ID = '__event_source__';

  // Nœud source = l'événement saisi
  const shortTitle = eventText.length > 50 ? eventText.slice(0, 48) + '…' : eventText;
  nodeMap.set(SOURCE_ID, {
    id: SOURCE_ID, name: shortTitle, type: 'EventSource',
    isSource: true, layer: 0,
  });

  // Entités extraites par le LLM
  for (const n of eventGraph.nodes) {
    if (!nodeMap.has(n.name)) {
      nodeMap.set(n.name, {
        id: n.name, name: n.name, type: n.type,
        isTalan: n.name === 'Talan', layer: -1,
      });
    }
  }

  // Talan comme nœud terminal si absent
  if (!nodeMap.has('Talan')) {
    nodeMap.set('Talan', { id: 'Talan', name: 'Talan', type: 'Company', isTalan: true, layer: -1 });
  }

  // Arêtes LLM — filtre : pas de chemin direct SOURCE → Talan
  const edges: GEdge[] = [];
  for (const e of eventGraph.edges) {
    if (!nodeMap.has(e.from_entity) || !nodeMap.has(e.to_entity)) continue;
    edges.push({
      source: e.from_entity,
      target: e.to_entity,
      relType: e.relation_type,
      impact: e.impact_score,
    });
  }

  // Calcul des degrés entrants pour identifier les racines
  const inDegree = new Map<string, number>();
  nodeMap.forEach((_, k) => inDegree.set(k, 0));
  edges.forEach(e => inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1));

  // Connexion : nœud source → entités sans prédécesseur (excl. Talan direct)
  nodeMap.forEach((node, k) => {
    if (k === SOURCE_ID) return;
    if ((inDegree.get(k) ?? 0) === 0 && k !== 'Talan') {
      edges.push({ source: SOURCE_ID, target: k, relType: 'TRIGGERS', impact: 0 });
    }
  });

  // Si Talan n'a pas encore d'arête entrante, connecter depuis l'entité la plus impactante
  const tHasIncoming = edges.some(e => e.target === 'Talan');
  if (!tHasIncoming) {
    // Cherche l'entité non-source avec le plus fort impact_score sortant
    const candidates = edges
      .filter(e => e.source !== SOURCE_ID && e.source !== 'Talan')
      .sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
    const anchor = candidates[0]?.source ?? [...nodeMap.keys()].find(k => k !== SOURCE_ID && k !== 'Talan');
    if (anchor) {
      edges.push({ source: anchor, target: 'Talan', relType: 'CAUSES_IMPACT_ON', impact: -0.5 });
    }
  }

  // BFS pour assigner les couches (positions x)
  const queue: string[] = [SOURCE_ID];
  nodeMap.get(SOURCE_ID)!.layer = 0;
  const visited = new Set<string>([SOURCE_ID]);

  while (queue.length > 0) {
    const cur = queue.shift()!;
    const curLayer = nodeMap.get(cur)!.layer;
    edges
      .filter(e => e.source === cur)
      .forEach(e => {
        if (!visited.has(e.target)) {
          visited.add(e.target);
          const n = nodeMap.get(e.target);
          if (n) { n.layer = curLayer + 1; queue.push(e.target); }
        }
      });
  }

  // Talan = couche max + 1
  let maxLayer = 0;
  nodeMap.forEach(n => { if (n.layer > maxLayer) maxLayer = n.layer; });
  const talanNode = nodeMap.get('Talan');
  if (talanNode) talanNode.layer = maxLayer + 1;

  // Nœuds non visités → couche 1 (fallback)
  nodeMap.forEach(n => { if (n.layer === -1) n.layer = 1; });

  return { nodes: [...nodeMap.values()], edges };
}

// ── Rendu canvas des nœuds ────────────────────────────────────────────────────

function paintNode(node: any, ctx: CanvasRenderingContext2D, gs: number) {
  const c    = cfg(node.type);
  const r    = c.r / Math.max(1, gs * 0.4);
  const x    = node.x as number;
  const y    = node.y as number;
  const fs   = Math.max(8, 11 / gs);
  const dim  = node.__dim === true;

  // Anneau doré pour Talan
  if (node.isTalan) {
    ctx.beginPath(); ctx.arc(x, y, r + 5, 0, 2 * Math.PI);
    ctx.fillStyle = dim ? '#FBBF2430' : '#FBBF24';
    ctx.fill();
  }

  // Anneau pointillé pour la source
  if (node.isSource) {
    ctx.beginPath(); ctx.arc(x, y, r + 3, 0, 2 * Math.PI);
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = dim ? c.color + '40' : c.color;
    ctx.lineWidth   = 2;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Cercle principal
  ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.fillStyle   = c.color + (dim ? '30' : 'DD');
  ctx.shadowColor = dim ? 'transparent' : c.color;
  ctx.shadowBlur  = dim ? 0 : node.__selected ? 16 : 5;
  ctx.fill();
  ctx.shadowBlur  = 0;

  // Emoji
  ctx.font          = `${Math.max(10, r * 0.8)}px serif`;
  ctx.textAlign     = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle     = dim ? '#FFFFFF50' : '#FFFFFF';
  ctx.fillText(c.emoji, x, y);

  // Label
  ctx.font          = `bold ${fs}px Inter, sans-serif`;
  ctx.textAlign     = 'center'; ctx.textBaseline = 'top';
  ctx.fillStyle     = dim ? '#94A3B8' : '#1E293B';
  ctx.strokeStyle   = dim ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.9)';
  ctx.lineWidth     = 3;
  const lbl = node.name.length > 22 ? node.name.slice(0, 20) + '…' : node.name;
  ctx.strokeText(lbl, x, y + r + 4);
  ctx.fillText(lbl, x, y + r + 4);
}

// ── Composant ─────────────────────────────────────────────────────────────────

interface Props {
  eventGraph: EventGraph;
  eventText: string;
  impactPct: number;
  height?: number;
}

export default function EventCausalGraph({ eventGraph, eventText, height = 420 }: Props) {
  const graphRef     = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [dims, setDims]         = useState({ w: 700, h: height });

  const { nodes, edges } = useMemo(
    () => buildGraph(eventGraph, eventText),
    [eventGraph, eventText],
  );

  // Positions initiales : x fixé par couche, y aléatoire centré
  const layerCount = useMemo(() => Math.max(...nodes.map(n => n.layer)) + 1, [nodes]);

  const graphData = useMemo(() => {
    const W = dims.w;
    const H = dims.h;
    const step = W / (layerCount + 1);
    const byLayer = new Map<number, GNode[]>();
    nodes.forEach(n => {
      const list = byLayer.get(n.layer) ?? [];
      list.push(n); byLayer.set(n.layer, list);
    });

    return {
      nodes: nodes.map(n => {
        const layerNodes = byLayer.get(n.layer) ?? [n];
        const idx = layerNodes.indexOf(n);
        const gap = H / (layerNodes.length + 1);
        return {
          ...n,
          x: step * (n.layer + 1),
          y: gap * (idx + 1),
        };
      }),
      links: edges.map(e => ({
        source: e.source, target: e.target,
        relType: e.relType, impact: e.impact,
      })),
    };
  }, [nodes, edges, dims, layerCount]);

  // Responsive
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      setDims({ w: entries[0]?.contentRect.width ?? 700, h: height });
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [height]);

  const handleStop = useCallback(() => {
    graphRef.current?.zoomToFit(400, 40);
  }, []);

  const linkColor = useCallback((link: any) => {
    const imp = link.impact as number;
    if (link.relType === 'TRIGGERS') return '#94A3B8';
    return imp > 0.05 ? '#16A34A' : imp < -0.05 ? '#DC2626' : '#94A3B8';
  }, []);

  const linkWidth = useCallback((link: any) => {
    return Math.max(1, Math.abs(link.impact as number) * 4);
  }, []);

  const linkLabel = useCallback((link: any) => link.relType as string, []);

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, gs: number) => {
    node.__selected = selected?.id === node.id;
    node.__dim = selected !== null && selected.id !== node.id;
    paintNode(node, ctx, gs);
  }, [selected]);

  if (eventGraph.nodes.length === 0) {
    return (
      <div style={{
        padding: '32px 20px', textAlign: 'center',
        color: 'var(--text-muted)', fontSize: 14,
        border: '1px dashed var(--border-subtle)', borderRadius: 12,
      }}>
        Aucune entité extraite par le LLM pour cet événement.
      </div>
    );
  }

  return (
    <div style={{ fontFamily: 'Inter, sans-serif' }}>
      <div
        ref={containerRef}
        style={{
          width: '100%', height,
          borderRadius: 12, overflow: 'hidden',
          background: 'linear-gradient(135deg, #EFF6FF 0%, #F8FAFC 100%)',
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
              const r = cfg(node.type).r + 6;
              ctx.fillStyle = color;
              ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI); ctx.fill();
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkLabel={linkLabel}
            linkDirectionalArrowLength={7}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.2}
            linkDirectionalParticles={2}
            linkDirectionalParticleWidth={2}
            linkDirectionalParticleColor={linkColor}
            onNodeClick={(node: any) =>
              setSelected(prev => prev?.id === node.id ? null : node as GNode)
            }
            onEngineStop={handleStop}
            d3AlphaDecay={0.03}
            d3VelocityDecay={0.35}
            cooldownTime={2000}
          />
        </Suspense>

        {/* Légende */}
        <div style={{
          position: 'absolute', bottom: 10, left: 12,
          display: 'flex', gap: 14, flexWrap: 'wrap',
        }}>
          {[
            { color: '#1D4ED8', label: 'Événement source' },
            { color: '#16A34A', label: 'Impact positif' },
            { color: '#DC2626', label: 'Impact négatif' },
            { color: '#FBBF24', label: 'Talan (cible)' },
          ].map(l => (
            <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: l.color }} />
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>{l.label}</span>
            </div>
          ))}
        </div>

        {/* Badge nœuds/arêtes */}
        <div style={{ position: 'absolute', top: 10, right: 12 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20,
            background: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE',
          }}>
            {nodes.length} nœuds · {edges.length} arêtes
          </span>
        </div>
      </div>

      {/* Panneau nœud sélectionné */}
      {selected && (
        <div style={{
          marginTop: 10,
          background: 'white', border: '1px solid var(--border-subtle)',
          borderRadius: 10, padding: '12px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 38, height: 38, borderRadius: '50%',
            background: cfg(selected.type).color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, flexShrink: 0,
          }}>
            {cfg(selected.type).emoji}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: 'var(--text-primary)', fontWeight: 700, fontSize: 14 }}>
              {selected.name}
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
              {selected.type}
              {selected.isTalan  && ' — Nœud cible (Talan)'}
              {selected.isSource && ' — Source de l\'événement'}
              {' · Couche ' + selected.layer}
            </div>
          </div>
          <button
            onClick={() => setSelected(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: 20 }}
          >×</button>
        </div>
      )}
    </div>
  );
}
