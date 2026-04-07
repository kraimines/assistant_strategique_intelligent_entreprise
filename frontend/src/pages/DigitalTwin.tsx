import { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Network, GitBranch, Globe, Lightbulb, Search, X, Database, ExternalLink } from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';
import AppShell from '../components/layout/AppShell';
import GlassCard from '../components/ui/GlassCard';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import { mockGraphData, mockInsights, departments } from '../data/mockGraph';
import type { GraphNode, AIInsight } from '../types';
import { useNavigate } from 'react-router-dom';

const tabs = [
  { id: 'graph', label: 'Knowledge Graph', icon: Network },
  { id: 'department', label: 'Départements', icon: GitBranch },
  { id: 'global', label: 'Vue Globale', icon: Globe },
  { id: 'insights', label: 'AI Insights', icon: Lightbulb },
  { id: 'data', label: 'Données', icon: Database },
];

const nodeTypeFilters = [
  { type: 'employee', label: 'Employés', color: '#00d4ff' },
  { type: 'department', label: 'Départements', color: '#7c3aed' },
  { type: 'project', label: 'Projets', color: '#10b981' },
  { type: 'client', label: 'Clients', color: '#f59e0b' },
  { type: 'opportunity', label: 'Opportunités', color: '#ec4899' },
  { type: 'supplier', label: 'Fournisseurs', color: '#6b7280' },
];

const severityConfig = {
  info: { label: 'Info', variant: 'cyan' as const, bg: 'bg-cyber-cyan/8', border: 'border-cyber-cyan/20' },
  warning: { label: 'Attention', variant: 'amber' as const, bg: 'bg-amber-500/8', border: 'border-amber-500/20' },
  critical: { label: 'Critique', variant: 'red' as const, bg: 'bg-red-500/8', border: 'border-red-500/20' },
};

const mockTables = [
  { name: 'hr.hr_employees', count: 50, domain: 'HR', color: 'cyan' as const },
  { name: 'hr.hr_leave_requests', count: 128, domain: 'HR', color: 'cyan' as const },
  { name: 'hr.hr_skills', count: 312, domain: 'HR', color: 'cyan' as const },
  { name: 'hr.hr_projects', count: 24, domain: 'HR', color: 'cyan' as const },
  { name: 'crm.crm_accounts', count: 47, domain: 'CRM', color: 'violet' as const },
  { name: 'crm.crm_opportunities', count: 89, domain: 'CRM', color: 'violet' as const },
  { name: 'crm.crm_contacts', count: 156, domain: 'CRM', color: 'violet' as const },
  { name: 'erp.erp_invoices', count: 342, domain: 'ERP', color: 'amber' as const },
  { name: 'erp.erp_sales_orders', count: 218, domain: 'ERP', color: 'amber' as const },
  { name: 'erp.erp_customers', count: 157, domain: 'ERP', color: 'amber' as const },
];

function KnowledgeGraphTab() {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [search, setSearch] = useState('');
  const [activeFilters, setActiveFilters] = useState<Set<string>>(
    new Set(nodeTypeFilters.map((f) => f.type))
  );
  const graphRef = useRef<{ zoom: (n: number) => void } | null>(null);

  const toggleFilter = (type: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const filteredData = {
    nodes: mockGraphData.nodes.filter(
      (n) =>
        activeFilters.has(n.type) &&
        (search === '' || n.label.toLowerCase().includes(search.toLowerCase()))
    ),
    links: mockGraphData.links.filter((l) => {
      const srcId = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
      const tgtId = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
      return (
        filteredData?.nodes.find((n) => n.id === srcId) &&
        filteredData?.nodes.find((n) => n.id === tgtId)
      );
    }),
  };

  const handleNodeClick = useCallback((node: object) => {
    setSelectedNode(node as GraphNode);
  }, []);

  return (
    <div className="flex h-full">
      {/* Controls */}
      <div className="w-56 flex-shrink-0 flex flex-col gap-3 p-4 border-r border-white/6">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un nœud"
            className="w-full pl-8 pr-3 py-2 rounded-xl text-xs bg-white/5 border border-white/10 text-white placeholder:text-white/25 focus:outline-none focus:border-cyber-cyan/40"
          />
        </div>

        <div className="space-y-1">
          <p className="text-white/40 text-[10px] uppercase tracking-wider mb-2">Filtrer par type</p>
          {nodeTypeFilters.map(({ type, label, color }) => (
            <button
              key={type}
              onClick={() => toggleFilter(type)}
              className={`
                w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs transition-all
                ${activeFilters.has(type) ? 'bg-white/8 text-white' : 'text-white/40 hover:bg-white/5'}
              `}
            >
              <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color, opacity: activeFilters.has(type) ? 1 : 0.3 }} />
              {label}
            </button>
          ))}
        </div>

        <div className="space-y-1">
          <p className="text-white/40 text-[10px] uppercase tracking-wider mb-2">Zoom</p>
          <div className="flex gap-1.5">
            <button
              onClick={() => (graphRef.current as { zoom: (n: number, d?: number) => void } | null)?.zoom?.(1.5, 400)}
              className="flex-1 py-1.5 rounded-lg bg-white/5 border border-white/8 text-white/50 text-xs hover:text-white hover:bg-white/10 transition-all"
            >
              +
            </button>
            <button
              onClick={() => (graphRef.current as { zoom: (n: number, d?: number) => void } | null)?.zoom?.(0.7, 400)}
              className="flex-1 py-1.5 rounded-lg bg-white/5 border border-white/8 text-white/50 text-xs hover:text-white hover:bg-white/10 transition-all"
            >
              −
            </button>
          </div>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1 relative overflow-hidden">
        <ForceGraph2D
          ref={graphRef as React.RefObject<ForceGraph2D>}
          graphData={filteredData}
          nodeLabel="label"
          nodeColor={(n: object) => (n as GraphNode).color}
          nodeVal={(n: object) => (n as GraphNode).size}
          linkColor={() => 'rgba(255,255,255,0.12)'}
          linkWidth={1}
          backgroundColor="transparent"
          onNodeClick={handleNodeClick}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node: object, ctx: CanvasRenderingContext2D) => {
            const n = node as GraphNode & { x?: number; y?: number };
            const fontSize = 9;
            ctx.font = `${fontSize}px Inter`;
            ctx.fillStyle = 'rgba(255,255,255,0.7)';
            ctx.textAlign = 'center';
            ctx.fillText(n.label, n.x || 0, (n.y || 0) + (n.size || 6) + 9);
          }}
          warmupTicks={100}
          cooldownTicks={50}
        />

        {/* Legend */}
        <div className="absolute bottom-4 left-4 flex flex-wrap gap-2">
          {nodeTypeFilters.map(({ type, label, color }) => (
            activeFilters.has(type) && (
              <div key={type} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg glass border border-white/8 text-[10px] text-white/50">
                <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                {label}
              </div>
            )
          ))}
        </div>
      </div>

      {/* Node panel */}
      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ x: 320, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 320, opacity: 0 }}
            transition={{ type: 'spring', damping: 25 }}
            className="w-72 flex-shrink-0 border-l border-white/6 p-4 overflow-y-auto"
            style={{ background: 'rgba(10,10,15,0.9)', backdropFilter: 'blur(20px)' }}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-white font-semibold text-sm">{selectedNode.label}</h3>
                <div className="mt-1">
                  <Badge
                    label={selectedNode.type}
                    variant={
                      { employee: 'cyan', department: 'violet', project: 'emerald', client: 'amber', opportunity: 'pink', supplier: 'gray' }[selectedNode.type] as 'cyan'
                    }
                  />
                </div>
              </div>
              <button onClick={() => setSelectedNode(null)} className="text-white/30 hover:text-white">
                <X size={16} />
              </button>
            </div>

            {selectedNode.metrics && Object.keys(selectedNode.metrics).length > 0 && (
              <div className="space-y-2 mb-4">
                <p className="text-white/40 text-[10px] uppercase tracking-wider">Métriques</p>
                {Object.entries(selectedNode.metrics).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center py-1.5 border-b border-white/5">
                    <span className="text-white/50 text-xs capitalize">{k}</span>
                    <span className="text-white/85 text-xs font-mono">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2">
              <p className="text-white/40 text-[10px] uppercase tracking-wider">Nœuds liés</p>
              {mockGraphData.links
                .filter((l) => {
                  const srcId = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
                  const tgtId = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
                  return srcId === selectedNode.id || tgtId === selectedNode.id;
                })
                .slice(0, 6)
                .map((l, i) => {
                  const srcId = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
                  const tgtId = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
                  const otherId = srcId === selectedNode.id ? tgtId : srcId;
                  const other = mockGraphData.nodes.find((n) => n.id === otherId);
                  return other ? (
                    <button
                      key={i}
                      onClick={() => setSelectedNode(other)}
                      className="w-full flex items-center gap-2 py-1.5 text-left hover:bg-white/5 rounded-lg px-2 transition-all"
                    >
                      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: other.color }} />
                      <span className="text-white/60 text-xs truncate">{other.label}</span>
                      <span className="text-white/25 text-[9px] ml-auto">{l.label}</span>
                    </button>
                  ) : null;
                })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DepartmentTab() {
  const [selected, setSelected] = useState<(typeof departments)[0] | null>(null);
  const svgWidth = 800;
  const svgHeight = 400;
  const centerX = svgWidth / 2;
  const centerY = 80;

  return (
    <div className="p-6">
      <GlassCard className="relative overflow-hidden">
        <svg width="100%" viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="max-h-96">
          {/* Lines from direction to others */}
          {departments.slice(1).map((d) => (
            <g key={d.id}>
              <line
                x1={departments[0].x}
                y1={departments[0].y + 30}
                x2={d.x}
                y2={d.y - 30}
                stroke="rgba(124,58,237,0.3)"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              {/* animated dot */}
              <circle r="3" fill="#7c3aed" opacity={0.8}>
                <animateMotion
                  dur={`${2 + Math.random() * 2}s`}
                  repeatCount="indefinite"
                  path={`M${departments[0].x},${departments[0].y + 30} L${d.x},${d.y - 30}`}
                />
              </circle>
            </g>
          ))}

          {departments.map((dept) => (
            <g
              key={dept.id}
              onClick={() => setSelected(dept)}
              style={{ cursor: 'pointer' }}
            >
              {/* Glow */}
              <circle cx={dept.x} cy={dept.y} r={38} fill="rgba(124,58,237,0.08)" />
              {/* Circle */}
              <circle
                cx={dept.x}
                cy={dept.y}
                r={30}
                fill="rgba(18,18,30,0.9)"
                stroke={selected?.id === dept.id ? '#7c3aed' : 'rgba(124,58,237,0.3)'}
                strokeWidth={selected?.id === dept.id ? 2 : 1}
              />
              <text
                x={dept.x}
                y={dept.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="white"
                fontSize={11}
                fontWeight={600}
              >
                {dept.name}
              </text>
              <text
                x={dept.x}
                y={dept.y + 14}
                textAnchor="middle"
                fill="rgba(0,212,255,0.8)"
                fontSize={9}
              >
                {dept.employeeCount} emp
              </text>
            </g>
          ))}
        </svg>

        {/* Selected department info */}
        <AnimatePresence>
          {selected && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="absolute bottom-4 right-4 w-64 p-4 rounded-xl"
              style={{ background: 'rgba(12,12,20,0.95)', border: '1px solid rgba(124,58,237,0.3)' }}
            >
              <div className="flex justify-between items-start mb-3">
                <h4 className="text-white font-semibold text-sm">{selected.name}</h4>
                <button onClick={() => setSelected(null)} className="text-white/30 hover:text-white"><X size={14} /></button>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-white/40">Manager</span><span className="text-white/80">{selected.manager}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Employés</span><span className="text-cyber-cyan">{selected.employeeCount}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Projets actifs</span><span className="text-cyber-emerald">{selected.activeProjects}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Budget</span><span className="text-cyber-amber">{selected.budget?.toLocaleString()} TND</span></div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </GlassCard>
    </div>
  );
}

function AIInsightsTab() {
  const navigate = useNavigate();

  return (
    <div className="p-6 space-y-4 max-w-4xl">
      {mockInsights.map((insight, i) => {
        const config = severityConfig[insight.severity];
        return (
          <motion.div
            key={insight.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className={`rounded-2xl p-5 border ${config.bg} ${config.border}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2.5 mb-2">
                  <Badge label={config.label} variant={config.variant} />
                  <Badge label={insight.category.toUpperCase()} variant="gray" />
                  {insight.value && (
                    <span className="text-white/40 text-xs font-mono">{insight.value}</span>
                  )}
                </div>
                <h3 className="text-white font-semibold text-sm mb-1.5">{insight.title}</h3>
                <p className="text-white/60 text-sm leading-relaxed">{insight.description}</p>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {insight.affectedEntities.map((e) => {
                    const node = mockGraphData.nodes.find((n) => n.id === e);
                    return node ? (
                      <span key={e} className="px-2 py-0.5 rounded-md bg-white/5 border border-white/8 text-white/50 text-[11px]">
                        {node.label}
                      </span>
                    ) : null;
                  })}
                </div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                icon={<ExternalLink size={12} />}
                onClick={() => navigate(`/chat?q=Parle-moi de: ${insight.title}`)}
              >
                Investiguer
              </Button>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

function DataTab() {
  return (
    <div className="p-6">
      <p className="text-white/40 text-sm mb-5">Aperçu des tables principales dans les bases de données PostgreSQL</p>
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
        {mockTables.map((t, i) => (
          <motion.div
            key={t.name}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <GlassCard hover glow={t.color} className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-white/50 text-[10px] uppercase tracking-wider mb-1">{t.domain}</p>
                  <p className="text-white text-sm font-mono font-medium">{t.name}</p>
                </div>
                <Database size={14} className="text-white/20 mt-0.5" />
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-2xl font-bold" style={{
                  color: t.color === 'cyan' ? '#00d4ff' : t.color === 'violet' ? '#7c3aed' : '#f59e0b'
                }}>{t.count}</span>
                <span className="text-white/30 text-xs">enregistrements</span>
              </div>
            </GlassCard>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

export default function DigitalTwin() {
  const [activeTab, setActiveTab] = useState('graph');

  return (
    <AppShell title="Digital Twin">
      <div className="flex flex-col h-full">
        {/* Tabs */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-white/6 overflow-x-auto">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`
                flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium whitespace-nowrap transition-all
                ${activeTab === id
                  ? 'bg-cyber-cyan/10 text-cyber-cyan border border-cyber-cyan/25'
                  : 'text-white/45 hover:text-white hover:bg-white/5'
                }
              `}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full overflow-y-auto"
            >
              {activeTab === 'graph' && <KnowledgeGraphTab />}
              {activeTab === 'department' && <DepartmentTab />}
              {activeTab === 'global' && (
                <div className="p-6">
                  <GlassCard animate className="p-8 text-center">
                    <Globe size={40} className="text-cyber-violet mx-auto mb-4 opacity-50" />
                    <p className="text-white/50">Vue Globale — Org chart interactif disponible dans la prochaine version</p>
                    <p className="text-white/25 text-sm mt-2">Utilisez le Knowledge Graph et la vue Départements pour explorer la structure</p>
                  </GlassCard>
                </div>
              )}
              {activeTab === 'insights' && <AIInsightsTab />}
              {activeTab === 'data' && <DataTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </AppShell>
  );
}
