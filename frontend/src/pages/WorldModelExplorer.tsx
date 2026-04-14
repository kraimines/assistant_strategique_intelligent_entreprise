/**
 * WorldModelExplorer.tsx — Enterprise Brain World Model visual explorer.
 *
 * Layout:
 *   [AppShell]
 *     Header bar (title, stats, refresh, actions)
 *     ─────────────────────────────────────────────
 *     LeftSidebar │ GraphViewer (canvas)  │ RightPanel
 *     ─────────────────────────────────────────────
 *     TimelineBar (collapsible)
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RefreshCw, Brain, Loader2, AlertTriangle, ChevronDown, ChevronUp,
} from 'lucide-react';

import AppShell from '../components/layout/AppShell';
import GraphViewer from '../components/WorldModel/GraphViewer';
import LeftSidebar from '../components/WorldModel/LeftSidebar';
import RightPanel from '../components/WorldModel/RightPanel';
import TimelineBar from '../components/WorldModel/TimelineBar';
import StatsBar from '../components/WorldModel/StatsBar';

import { graphApi } from '../api/graphApi';
import type { GraphNode, GraphLink, TimelineEvent, SearchResult } from '../api/graphApi';

// ── Component ──────────────────────────────────────────────────────────────────

export default function WorldModelExplorer() {
  // ── Graph data ──
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── View / filters ──
  const [activeView, setActiveView] = useState('org');
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());

  // ── Selected node ──
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  // ── Focus mode (search) ── when set, graph shows only this node + its neighbours
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [, setFocusNeighbourIds] = useState<Set<string>>(new Set());
  // Backup of full graph data to restore when exiting focus mode
  const fullGraphRef = useRef<{ nodes: GraphNode[]; links: GraphLink[] }>({ nodes: [], links: [] });

  // ── Timeline ──
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [timelineOpen, setTimelineOpen] = useState(true);

  // ── Load graph ──────────────────────────────────────────────────────────────
  const loadGraph = useCallback(async (view: string) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setHighlightId(null);
    try {
      const data = await graphApi.getWorld(view);
      setNodes(data.nodes);
      setLinks(data.links);
      fullGraphRef.current = { nodes: data.nodes, links: data.links };
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err?.message ?? 'Erreur Neo4j');
      setNodes([]);
      setLinks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load timeline once
  useEffect(() => {
    graphApi.getTimeline()
      .then(d => setEvents(d.events))
      .catch(() => {/* timeline is non-critical */});
  }, []);

  // Load graph whenever view changes
  useEffect(() => { loadGraph(activeView); }, [activeView, loadGraph]);

  // ── Handlers ────────────────────────────────────────────────────────────────
  const clearFocus = useCallback(() => {
    setFocusNodeId(null);
    setFocusNeighbourIds(new Set());
    // Restore full graph
    if (fullGraphRef.current.nodes.length > 0) {
      setNodes(fullGraphRef.current.nodes);
      setLinks(fullGraphRef.current.links);
    }
  }, []);

  const handleViewChange = (view: string) => {
    setActiveView(view);
    setActiveFilters(new Set());
    clearFocus();
  };

  const handleFilterToggle = useCallback((type: string) => {
    setActiveFilters(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  }, []);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setHighlightId(node.id);
  }, []);

  const handleSearchSelect = useCallback(async (result: SearchResult) => {
    const rootNode: GraphNode = { id: result.id, label: result.label, name: result.name, props: result.props };
    setSelectedNode(rootNode);
    setHighlightId(result.id);
    setFocusNodeId(result.id);
    setFocusNeighbourIds(new Set([result.id]));
    // Save full graph before replacing it
    fullGraphRef.current = { nodes, links };

    try {
      const detail = await graphApi.getNodeDetail(result.id);

      // Build synthetic neighbour nodes from the detail relations
      const syntheticNodes: GraphNode[] = [rootNode];
      const syntheticLinks: GraphLink[] = [];
      const usedIds = new Set<string>([result.id]);

      detail.relations.forEach((rel, i) => {
        // Try to find a real matching node in the loaded graph first
        const existing = nodes.find(n => n.name === rel.name && n.label === rel.label);
        const nbId = existing ? existing.id : `__nb_${i}__${rel.name}`;

        if (!usedIds.has(nbId)) {
          usedIds.add(nbId);
          syntheticNodes.push({
            id: nbId,
            label: rel.label ?? 'Node',
            name: rel.name ?? nbId,
            props: {},
          });
        }

        const src = rel.direction === 'out' ? result.id : nbId;
        const tgt = rel.direction === 'out' ? nbId : result.id;
        syntheticLinks.push({ source: src, target: tgt, type: rel.type });
      });

      // Replace graph data with this focused subgraph
      setNodes(syntheticNodes);
      setLinks(syntheticLinks);
      setFocusNodeId(result.id);
      setFocusNeighbourIds(usedIds);
    } catch {
      setFocusNeighbourIds(new Set([result.id]));
    }
  }, [nodes]);

  const handleEventClick = useCallback((ev: TimelineEvent) => {
    const found = nodes.find(n => n.id === ev.entity_id);
    if (found) {
      setSelectedNode(found);
      setHighlightId(found.id);
    }
  }, [nodes]);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <AppShell title="World Model Explorer">
      <div className="flex flex-col h-full" style={{ minHeight: 0 }}>

        {/* ── Top bar ── */}
        <div
          className="flex items-center justify-between px-5 py-3 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center">
              <Brain size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold leading-none" style={{ color: 'var(--text-primary)' }}>
                Enterprise Brain — World Model
              </h1>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Graphe Neo4j en temps réel</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <StatsBar nodeCount={nodes.length} linkCount={links.length} view={activeView} />
            <button
              onClick={() => loadGraph(activeView)}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-cyber-cyan border border-cyber-cyan/30 hover:bg-cyber-cyan/10 transition-all disabled:opacity-40"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Actualiser
            </button>
          </div>
        </div>

        {/* ── Error banner ── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="flex items-center gap-3 px-5 py-2.5 bg-red-500/10 border-b border-red-500/20 text-sm text-red-300"
            >
              <AlertTriangle size={14} />
              <span>{error}</span>
              <span className="text-red-400/60 text-xs ml-2">
                Vérifiez que Neo4j est démarré (bolt://localhost:7687)
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Main 3-column layout ── */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar */}
          <LeftSidebar
            activeView={activeView}
            onViewChange={handleViewChange}
            activeFilters={activeFilters}
            onFilterToggle={handleFilterToggle}
            onSearchSelect={handleSearchSelect}
          />

          {/* Graph canvas */}
          <div className="flex-1 relative overflow-hidden">
            {loading && (
              <div className="absolute inset-0 flex flex-col items-center justify-center z-20 gap-3"
                style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(4px)' }}>
                <Loader2 size={32} className="text-cyber-cyan animate-spin" />
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Chargement du graphe Neo4j…</p>
              </div>
            )}
            {/* Focus mode banner */}
            {focusNodeId && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-4 py-2 rounded-full text-sm"
                style={{ background: 'rgba(124,58,237,0.9)', border: '1px solid rgba(124,58,237,0.5)', backdropFilter: 'blur(8px)' }}>
                <span className="text-white/80">Focus :</span>
                <span className="text-white font-semibold">{selectedNode?.name}</span>
                <button onClick={() => { clearFocus(); setSelectedNode(null); setHighlightId(null); }}
                  className="ml-2 text-white/60 hover:text-white text-xs underline">
                  Voir tout le graphe
                </button>
              </div>
            )}

            {!loading && !error && (
              <GraphViewer
                nodes={nodes}
                links={links}
                activeFilters={focusNodeId ? new Set() : activeFilters}
                highlightId={highlightId}
                onNodeClick={handleNodeClick}
                excludeLabels={[
                  'PerformanceReview',
                  ...(activeView === 'org' && !focusNodeId ? ['Skill'] : []),
                ]}
              />
            )}
            {!loading && error && nodes.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <div className="text-5xl">🕸️</div>
                <p className="text-white/30 text-sm text-center max-w-xs">
                  Impossible de charger le graphe.<br />
                  Assurez-vous que Docker est démarré et Neo4j accessible.
                </p>
                <button
                  onClick={() => loadGraph(activeView)}
                  className="px-4 py-2 rounded-lg text-sm text-cyber-cyan border border-cyber-cyan/30 hover:bg-cyber-cyan/10"
                >
                  Réessayer
                </button>
              </div>
            )}

            {/* Node count badge */}
            {!loading && nodes.length > 0 && (
              <div
                className="absolute bottom-4 left-4 text-xs px-3 py-1.5 rounded-full"
                style={{ background: 'var(--bg-overlay-card)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
              >
                {nodes.length} nœuds · {links.length} relations
              </div>
            )}
          </div>

          {/* Right detail panel */}
          <RightPanel
            node={selectedNode}
            onClose={() => { setSelectedNode(null); setHighlightId(null); }}
          />
        </div>

        {/* ── Timeline bar ── */}
        {events.length > 0 && (
          <div className="flex-shrink-0" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
            <button
              onClick={() => setTimelineOpen(v => !v)}
              className="w-full flex items-center justify-between px-5 py-1.5 text-xs text-white/30 hover:text-white/50 transition-colors"
            >
              <span className="uppercase tracking-widest font-semibold">Événements récents</span>
              {timelineOpen ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
            </button>
            <AnimatePresence>
              {timelineOpen && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="overflow-hidden"
                >
                  <TimelineBar events={events} onEventClick={handleEventClick} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </AppShell>
  );
}
