/**
 * PipelineStatusBar — live pipeline state strip.
 * Pastel light version with stronger readability.
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

  const statusLabel = isCycleRunning ? 'En cours' : isSchedulerActive ? 'Planifié' : 'Inactif';
  const statusColor = isCycleRunning ? '#059669' : isSchedulerActive ? '#2563EB' : '#94A3B8';
  const statusBg = isCycleRunning ? '#ECFDF5' : isSchedulerActive ? '#EFF6FF' : '#F8FAFC';
  const statusBdr = isCycleRunning ? 'rgba(5,150,105,0.25)' : isSchedulerActive ? 'rgba(37,99,235,0.22)' : 'var(--border-subtle)';

  const kpis = [
    { icon: <Database size={14} />, label: 'Articles', value: status?.articles_in_db?.toLocaleString() ?? '—', color: '#2563EB' },
    { icon: <GitBranch size={14} />, label: 'Nœuds KG', value: status?.kg_nodes?.toLocaleString() ?? '—', color: '#7C3AED' },
    { icon: <GitBranch size={14} />, label: 'Relations KG', value: status?.kg_relations?.toLocaleString() ?? '—', color: '#059669' },
    { icon: <Clock size={14} />, label: 'Dernier cycle', value: fmtDate(status?.last_run_at ?? null), color: '#D97706' },
    { icon: <Clock size={14} />, label: 'Prochain cycle', value: fmtDate(status?.next_run_at ?? null), color: '#94A3B8' },
  ];

  return (
    <div
      className="rounded-2xl p-4 flex flex-wrap items-center gap-4"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div className="flex items-center gap-2.5 flex-shrink-0">
        <div
          className="relative w-10 h-10 rounded-2xl flex items-center justify-center"
          style={{ background: statusBg, border: `1px solid ${statusBdr}` }}
        >
          <Activity size={15} style={{ color: statusColor }} />
          {(isCycleRunning || isSchedulerActive) && (
            <span
              className="absolute top-0.5 right-0.5 w-2.5 h-2.5 rounded-full"
              style={{
                background: statusColor,
                animation: isCycleRunning ? 'pulse 1.5s infinite' : 'none',
              }}
            />
          )}
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: 'var(--text-faint)' }}>
            Pipeline
          </p>
          <p className="text-base font-bold mt-0.5" style={{ color: statusColor }}>
            {statusLabel}
          </p>
          {isSchedulerActive && status?.next_run_at && !isCycleRunning && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-faint)' }}>
              prochain : {new Date(status.next_run_at).toLocaleTimeString('fr-FR', {
                hour: '2-digit', minute: '2-digit',
              })}
            </p>
          )}
        </div>
      </div>

      <div className="w-px h-10 flex-shrink-0" style={{ background: 'var(--border-subtle)' }} />

      <div className="flex flex-wrap items-center gap-5 flex-1 min-w-0">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="flex items-center gap-2 min-w-0">
            <span style={{ color: kpi.color }}>{kpi.icon}</span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap" style={{ color: 'var(--text-faint)' }}>
                {kpi.label}
              </p>
              <p className="text-sm font-bold mt-0.5 whitespace-nowrap" style={{ color: kpi.color }}>
                {loading
                  ? <span className="inline-block w-10 h-3 rounded animate-pulse" style={{ background: 'var(--border-subtle)' }} />
                  : kpi.value}
              </p>
            </div>
          </div>
        ))}
      </div>

      <AnimatePresence>
        {status?.errors_last_run && status.errors_last_run.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold"
            style={{
              background: 'var(--danger-subtle)',
              color: 'var(--danger)',
              border: '1px solid rgba(239,68,68,0.18)',
            }}
          >
            <AlertTriangle size={13} />
            <span>{status.errors_last_run.length} erreur(s)</span>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        onClick={onRunNow}
        disabled={isCycleRunning}
        className="flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-bold transition-all duration-200 flex-shrink-0"
        style={{
          background: isCycleRunning ? 'var(--bg-base)' : 'var(--primary-subtle)',
          color: isCycleRunning ? 'var(--text-faint)' : 'var(--primary-dark)',
          border: isCycleRunning ? '1px solid var(--border-subtle)' : '1px solid var(--primary-muted)',
          cursor: isCycleRunning ? 'not-allowed' : 'pointer',
        }}
      >
        {isCycleRunning ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
        {isCycleRunning ? 'Analyse…' : 'Lancer maintenant'}
      </button>
    </div>
  );
}
