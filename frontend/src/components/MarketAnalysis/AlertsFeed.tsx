/**
 * AlertsFeed — real-time market alerts sorted by severity.
 * Each card shows: level badge, title, talan_impact_score gauge,
 * affected entities, recommended action, and timestamp.
 */
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldAlert, TrendingDown, TrendingUp, Minus, ChevronDown, ChevronUp, Eye } from 'lucide-react';
import { useState } from 'react';
import type { MarketAlert } from '../../api/marketAnalysisApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  alerts: MarketAlert[];
  loading: boolean;
}

const LEVEL_CONFIG = {
  critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.25)', label: 'CRITIQUE' },
  high:     { color: '#f97316', bg: 'rgba(249,115,22,0.10)', border: 'rgba(249,115,22,0.25)', label: 'HAUTE' },
  medium:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.25)', label: 'MODÉRÉE' },
  low:      { color: '#10b981', bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.25)', label: 'FAIBLE' },
};

function ImpactBar({ score }: { score: number }) {
  const abs = Math.abs(score);
  const color = score < -0.4 ? '#ef4444' : score < 0 ? '#f97316' : score > 0.4 ? '#10b981' : '#f59e0b';
  const width = `${Math.round(abs * 100)}%`;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-white/8 relative overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="absolute top-0 h-full rounded-full"
          style={{ background: color, [score < 0 ? 'right' : 'left']: 0 }}
        />
      </div>
      <span className="text-xs font-mono font-semibold" style={{ color }}>
        {score >= 0 ? '+' : ''}{score.toFixed(2)}
      </span>
    </div>
  );
}

function AlertCard({ alert }: { alert: MarketAlert }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = LEVEL_CONFIG[alert.level] ?? LEVEL_CONFIG.low;
  const id = alert.alert_id ?? alert.id ?? '';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl overflow-hidden"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: `${cfg.color}20`, color: cfg.color }}>
          <ShieldAlert size={15} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-md"
              style={{ background: `${cfg.color}20`, color: cfg.color }}>
              {cfg.label}
            </span>
            <span className="text-white/30 text-[10px]">
              {new Date(alert.generated_at).toLocaleString('fr-FR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          </div>
          <p className="text-sm font-medium text-white/85 leading-snug line-clamp-2">{alert.title}</p>
          {alert.summary && (
            <p className="text-xs text-white/45 mt-1 leading-relaxed line-clamp-2">{alert.summary}</p>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 p-1.5 rounded-lg text-white/30 hover:text-white/60 hover:bg-white/5 transition-all"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Impact bar */}
      <div className="px-4 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-white/35">Impact sur Talan</span>
          {alert.talan_impact_score < 0
            ? <TrendingDown size={11} className="text-red-400" />
            : alert.talan_impact_score > 0
            ? <TrendingUp size={11} className="text-emerald-400" />
            : <Minus size={11} className="text-white/30" />}
        </div>
        <ImpactBar score={alert.talan_impact_score} />
      </div>

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t" style={{ borderColor: `${cfg.border}` }}>
              {/* Affected entities */}
              {alert.affected_entities?.length > 0 && (
                <div className="pt-3">
                  <p className="text-[10px] text-white/30 mb-1.5">Entités affectées</p>
                  <div className="flex flex-wrap gap-1.5">
                    {alert.affected_entities.map((e) => (
                      <span key={e} className="px-2 py-0.5 rounded-md text-[10px]"
                        style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.55)' }}>
                        {e}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {/* Recommended action */}
              {alert.talan_recommended_action && (
                <div className="flex items-start gap-2 p-2.5 rounded-lg"
                  style={{ background: 'rgba(255,255,255,0.04)' }}>
                  <Eye size={12} className="text-cyan-400 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-white/60 leading-relaxed">{alert.talan_recommended_action}</p>
                </div>
              )}
              {/* Hidden GNN risks */}
              {alert.gnn_hidden_risks?.length > 0 && (
                <div>
                  <p className="text-[10px] text-white/30 mb-1">Risques cachés GNN</p>
                  <div className="flex flex-wrap gap-1.5">
                    {alert.gnn_hidden_risks.map((r) => (
                      <span key={r} className="px-2 py-0.5 rounded-md text-[10px]"
                        style={{ background: 'rgba(124,58,237,0.15)', color: '#a78bfa' }}>
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function AlertsFeed({ alerts, loading }: Props) {
  const [filter, setFilter] = useState<string>('all');

  const levels = ['all', 'critical', 'high', 'medium', 'low'] as const;
  const filtered = filter === 'all' ? alerts : alerts.filter((a) => a.level === filter);

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-xl bg-white/3 border border-white/6 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Filter tabs */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {levels.map((lv) => {
          const cfg = lv === 'all' ? null : LEVEL_CONFIG[lv];
          const count = lv === 'all' ? alerts.length : alerts.filter((a) => a.level === lv).length;
          return (
            <button
              key={lv}
              onClick={() => setFilter(lv)}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all"
              style={{
                background: filter === lv
                  ? cfg ? `${cfg.color}18` : 'rgba(255,255,255,0.08)'
                  : 'transparent',
                color: filter === lv
                  ? cfg ? cfg.color : 'rgba(255,255,255,0.8)'
                  : 'rgba(255,255,255,0.35)',
                border: `1px solid ${filter === lv ? (cfg ? cfg.border : 'rgba(255,255,255,0.15)') : 'transparent'}`,
              }}
            >
              {lv === 'all' ? 'Toutes' : LEVEL_CONFIG[lv].label}
              <span className="text-[10px] opacity-60">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Alert cards */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <ShieldAlert size={32} className="text-white/15" />
          <p className="text-white/30 text-sm">Aucune alerte</p>
        </div>
      ) : (
        <AnimatePresence>
          {filtered.map((alert) => (
            <AlertCard key={alert.alert_id ?? alert.id ?? alert.title} alert={alert} />
          ))}
        </AnimatePresence>
      )}
    </div>
  );
}
