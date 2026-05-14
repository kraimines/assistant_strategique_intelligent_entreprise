/**
 * WorldModelExplorer.tsx — Enterprise Brain World Model visual explorer.
 *
 * Layout:
 *   [AppShell]
 *     Header bar (title, stats, refresh)
 *     ──────────────────────────────────────
 *     LeftSidebar │ GraphViewer (canvas) │ RightPanel
 *     ──────────────────────────────────────
 *     TimelineBar (collapsible)
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RefreshCw, Brain, Loader2, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

import AppShell    from '../components/layout/AppShell';
import GraphViewer from '../components/WorldModel/GraphViewer';
import LeftSidebar from '../components/WorldModel/LeftSidebar';
import RightPanel  from '../components/WorldModel/RightPanel';
import TimelineBar from '../components/WorldModel/TimelineBar';
import StatsBar    from '../components/WorldModel/StatsBar';

import { graphApi }                                          from '../api/graphApi';
import type { GraphNode, GraphLink, TimelineEvent, SearchResult } from '../api/graphApi';

export default function WorldModelExplorer() {
  /* ── Graph state ──────────────────────────────────────────────────────── */
  const [nodes,   setNodes]   = useState<GraphNode[]>([]);
  const [links,   setLinks]   = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  /* ── View / filters ───────────────────────────────────────────────────── */
  const [activeView,    setActiveView]    = useState('org');
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());

  /* ── Selection & focus ────────────────────────────────────────────────── */
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightId,  setHighlightId]  = useState<string | null>(null);
  const [focusNodeId,  setFocusNodeId]  = useState<string | null>(null);
  const [, setFocusNeighbourIds]        = useState<Set<string>>(new Set());
  const fullGraphRef = useRef<{ nodes: GraphNode[]; links: GraphLink[] }>({ nodes: [], links: [] });

  /* ── Timeline ─────────────────────────────────────────────────────────── */
  const [events,       setEvents]       = useState<TimelineEvent[]>([]);
  const [timelineOpen, setTimelineOpen] = useState(true);

  /* ── Load graph ───────────────────────────────────────────────────────── */
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

  useEffect(() => {
    graphApi.getTimeline()
      .then(d => setEvents(d.events))
      .catch(() => {});
  }, []);

  useEffect(() => { loadGraph(activeView); }, [activeView, loadGraph]);

  /* ── Handlers ─────────────────────────────────────────────────────────── */
  const clearFocus = useCallback(() => {
    setFocusNodeId(null);
    setFocusNeighbourIds(new Set());
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
    fullGraphRef.current = { nodes, links };

    try {
      const detail = await graphApi.getNodeDetail(result.id);
      const syntheticNodes: GraphNode[] = [rootNode];
      const syntheticLinks: GraphLink[] = [];
      const usedIds = new Set<string>([result.id]);

      detail.relations.forEach((rel, i) => {
        const existing = nodes.find(n => n.name === rel.name && n.label === rel.label);
        const nbId = existing ? existing.id : `__nb_${i}__${rel.name}`;
        if (!usedIds.has(nbId)) {
          usedIds.add(nbId);
          syntheticNodes.push({ id: nbId, label: rel.label ?? 'Node', name: rel.name ?? nbId, props: {} });
        }
        const src = rel.direction === 'out' ? result.id : nbId;
        const tgt = rel.direction === 'out' ? nbId : result.id;
        syntheticLinks.push({ source: src, target: tgt, type: rel.type });
      });

      setNodes(syntheticNodes);
      setLinks(syntheticLinks);
      setFocusNodeId(result.id);
      setFocusNeighbourIds(usedIds);
    } catch {
      setFocusNeighbourIds(new Set([result.id]));
    }
  }, [nodes, links]);

  const handleEventClick = useCallback((ev: TimelineEvent) => {
    const found = nodes.find(n => n.id === ev.entity_id);
    if (found) { setSelectedNode(found); setHighlightId(found.id); }
  }, [nodes]);

  /* ── Render ───────────────────────────────────────────────────────────── */
  return (
    <AppShell title="World Model Explorer">
      <div className="flex flex-col h-full" style={{ minHeight: 0, background: 'var(--bg-base)' }}>

        {/* ── Top bar ───────────────────────────────────────────────────── */}
        <div
          className="flex items-center justify-between px-5 py-3.5 flex-shrink-0"
          style={{
            background:   'var(--bg-surface)',
            borderBottom: '1px solid var(--border-subtle)',
            boxShadow:    '0 1px 3px rgba(15,23,42,0.05)',
          }}
        >
          {/* Title + icon */}
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{
                background: 'linear-gradient(135deg, #3B82F6, #14B8A6)',
                boxShadow:  '0 2px 8px rgba(59,130,246,0.22)',
              }}
            >
              <Brain size={17} color="#fff" />
            </div>
            <div>
              <h1 className="text-base font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
                Enterprise Brain — World Model
              </h1>
              <p className="text-xs mt-0.5 font-medium" style={{ color: 'var(--text-muted)' }}>
                Graphe Neo4j en temps réel
              </p>
            </div>
          </div>

          {/* Stats + refresh */}
          <div className="flex items-center gap-4">
            <StatsBar nodeCount={nodes.length} linkCount={links.length} view={activeView} />
            <button
              onClick={() => loadGraph(activeView)}
              disabled={loading}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-40"
              style={{
                background:  'var(--primary-subtle)',
                border:      '1px solid var(--primary-muted)',
                color:       'var(--primary-dark)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-muted)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-subtle)';
              }}
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Actualiser
            </button>
          </div>
        </div>

        {/* ── Error banner ──────────────────────────────────────────────── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="flex items-center gap-3 px-5 py-3 text-sm border-b flex-shrink-0"
              style={{
                background:  'var(--danger-subtle)',
                borderColor: 'rgba(239,68,68,0.25)',
                color:       'var(--danger)',
              }}
            >
              <AlertTriangle size={15} className="flex-shrink-0" />
              <span className="font-medium">{error}</span>
              <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
                Vérifiez que Neo4j est démarré (bolt://localhost:7687)
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Main 3-column layout ──────────────────────────────────────── */}
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
          <div className="flex-1 relative overflow-hidden" style={{ background: '#F1F5F9' }}>

            {/* Loading overlay */}
            {loading && (
              <div
                className="absolute inset-0 flex flex-col items-center justify-center z-20 gap-3"
                style={{ background: 'rgba(241,245,249,0.85)', backdropFilter: 'blur(4px)' }}
              >
                <Loader2 size={32} className="animate-spin" style={{ color: 'var(--primary)' }} />
                <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Chargement du graphe Neo4j…
                </p>
              </div>
            )}

            {/* Focus mode banner */}
            {focusNodeId && (
              <div
                className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 px-4 py-2 rounded-full text-sm"
                style={{
                  background:    'rgba(59,130,246,0.92)',
                  border:        '1px solid rgba(59,130,246,0.5)',
                  backdropFilter:'blur(8px)',
                  boxShadow:     '0 4px 16px rgba(59,130,246,0.25)',
                }}
              >
                <span className="font-medium" style={{ color: 'rgba(219,234,254,0.9)' }}>Focus :</span>
                <span className="font-bold text-white">{selectedNode?.name}</span>
                <button
                  onClick={() => { clearFocus(); setSelectedNode(null); setHighlightId(null); }}
                  className="ml-2 text-blue-200 hover:text-white text-xs underline transition-colors"
                >
                  Voir tout le graphe
                </button>
              </div>
            )}

            {/* Graph */}
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

            {/* Empty / error state */}
            {!loading && error && nodes.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <div className="text-5xl">🕸️</div>
                <p className="text-sm text-center max-w-xs font-medium" style={{ color: 'var(--text-muted)' }}>
                  Impossible de charger le graphe.<br />
                  Assurez-vous que Docker est démarré et Neo4j accessible.
                </p>
                <button
                  onClick={() => loadGraph(activeView)}
                  className="px-4 py-2 rounded-xl text-sm font-semibold transition-all"
                  style={{
                    background: 'var(--primary-subtle)',
                    border:     '1px solid var(--primary-muted)',
                    color:      'var(--primary-dark)',
                  }}
                >
                  Réessayer
                </button>
              </div>
            )}

            {/* Node / link count badge */}
            {!loading && nodes.length > 0 && (
              <div
                className="absolute bottom-4 left-4 text-xs px-3 py-1.5 rounded-full font-medium"
                style={{
                  background: 'var(--bg-surface)',
                  border:     '1px solid var(--border-subtle)',
                  color:      'var(--text-muted)',
                  boxShadow:  'var(--shadow-card)',
                }}
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

        {/* ── Timeline bar ──────────────────────────────────────────────── */}
        {events.length > 0 && (
          <div
            className="flex-shrink-0"
            style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-surface)' }}
          >
            {/* Toggle header */}
            <button
              onClick={() => setTimelineOpen(v => !v)}
              className="w-full flex items-center justify-between px-5 py-2 transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
              }}
            >
              <span className="text-xs font-bold uppercase tracking-widest">
                Événements récents
              </span>
              {timelineOpen
                ? <ChevronDown size={13} />
                : <ChevronUp size={13} />}
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
