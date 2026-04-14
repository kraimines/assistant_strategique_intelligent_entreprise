/**
 * PipelineStatusBar — sticky top strip showing live pipeline state.
 * Shows: running indicator, last run, next run, article count, KG nodes/rels.
 */
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Database, GitBranch, Clock, RefreshCw, AlertTriangle, Play } from 'lucide-react';
import type { PipelineStatus } from '../../api/marketAnalysisApi';

interface Props {
  status: PipelineStatus | undefined;
  loading: boolean;
  onRunNow: () => void;
  running: boolean;
}

function fmtDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export default function PipelineStatusBar({ status, loading, onRunNow, running }: Props) {
  const isSchedulerActive = status?.running ?? false;
  const isCycleRunning = status?.cycle_running || running;

  // Three states: cycle executing / scheduler idle / scheduler inactive
  const statusLabel = isCycleRunning ? 'En cours' : isSchedulerActive ? 'Planifié' : 'Inactif';
  const statusColor = isCycleRunning ? '#10b981' : isSchedulerActive ? '#00d4ff' : 'rgba(255,255,255,0.3)';
  const dotColor   = isCycleRunning ? 'bg-emerald-400 animate-pulse' : isSchedulerActive ? 'bg-cyan-400' : 'bg-white/20';

  const kpis = [
    {
      icon: <Database size={13} />,
      label: 'Articles',
      value: status?.articles_in_db?.toLocaleString() ?? '—',
      color: '#00d4ff',
    },
    {
      icon: <GitBranch size={13} />,
      label: 'Nœuds KG',
      value: status?.kg_nodes?.toLocaleString() ?? '—',
      color: '#7c3aed',
    },
    {
      icon: <GitBranch size={13} />,
      label: 'Relations KG',
      value: status?.kg_relations?.toLocaleString() ?? '—',
      color: '#10b981',
    },
    {
      icon: <Clock size={13} />,
      label: 'Dernier cycle',
      value: fmtDate(status?.last_run_at ?? null),
      color: '#f59e0b',
    },
    {
      icon: <Clock size={13} />,
      label: 'Prochain cycle',
      value: fmtDate(status?.next_run_at ?? null),
      color: 'rgba(255,255,255,0.4)',
    },
  ];

  return (
    <div
      className="glass rounded-2xl p-4 flex flex-wrap items-center gap-4"
      style={{ border: '1px solid var(--border-subtle)' }}
    >
      {/* Status pill */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="relative flex items-center justify-center w-8 h-8 rounded-xl"
          style={{ background: isCycleRunning ? 'rgba(16,185,129,0.12)' : isSchedulerActive ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.05)' }}>
          <Activity size={15} style={{ color: statusColor }} />
          {(isCycleRunning || isSchedulerActive) && (
            <span className={`absolute top-0.5 right-0.5 w-2 h-2 rounded-full ${dotColor}`} />
          )}
        </div>
        <div>
          <p className="text-[10px] text-white/40 leading-none">Pipeline</p>
          <p className="text-xs font-semibold mt-0.5" style={{ color: statusColor }}>
            {statusLabel}
          </p>
          {isSchedulerActive && status?.next_run_at && !isCycleRunning && (
            <p className="text-[9px] text-white/25 leading-none mt-0.5">
              prochain : {new Date(status.next_run_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
            </p>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="w-px h-8 bg-white/6 flex-shrink-0" />

      {/* KPIs */}
      <div className="flex flex-wrap items-center gap-5 flex-1 min-w-0">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="flex items-center gap-1.5 min-w-0">
            <span style={{ color: kpi.color }}>{kpi.icon}</span>
            <div className="min-w-0">
              <p className="text-[9px] text-white/30 leading-none whitespace-nowrap">{kpi.label}</p>
              <p className="text-xs font-medium mt-0.5 whitespace-nowrap" style={{ color: kpi.color }}>
                {loading ? <span className="inline-block w-10 h-3 bg-white/10 rounded animate-pulse" /> : kpi.value}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Errors badge */}
      <AnimatePresence>
        {status?.errors_last_run && status.errors_last_run.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs"
            style={{ background: 'rgba(239,68,68,0.10)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.20)' }}
          >
            <AlertTriangle size={12} />
            <span>{status.errors_last_run.length} erreur(s)</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Run now button */}
      <button
        onClick={onRunNow}
        disabled={isCycleRunning}
        className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-200 flex-shrink-0"
        style={{
          background: isCycleRunning ? 'rgba(255,255,255,0.05)' : 'rgba(0,212,255,0.12)',
          color: isCycleRunning ? 'rgba(255,255,255,0.3)' : '#00d4ff',
          border: isCycleRunning ? '1px solid rgba(255,255,255,0.08)' : '1px solid rgba(0,212,255,0.25)',
          cursor: isCycleRunning ? 'not-allowed' : 'pointer',
        }}
      >
        {isCycleRunning
          ? <RefreshCw size={13} className="animate-spin" />
          : <Play size={13} />}
        {isCycleRunning ? 'Analyse…' : 'Lancer maintenant'}
      </button>
    </div>
  );
}
