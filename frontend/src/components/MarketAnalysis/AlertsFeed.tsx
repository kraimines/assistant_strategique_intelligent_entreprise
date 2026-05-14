/**
 * AlertsFeed — real-time market alerts.
 * Light pastel palette with readable dark text and larger fonts.
 */
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldAlert, TrendingDown, TrendingUp, Minus,
  ChevronDown, ChevronUp, Eye,
} from 'lucide-react';
import { useState } from 'react';
import type { MarketAlert } from '../../api/marketAnalysisApi';

interface Props { alerts: MarketAlert[]; loading: boolean }

const LEVEL_CONFIG: Record<string, { color: string; bg: string; border: string; label: string; textColor: string }> = {
  critical: { color: '#DC2626', bg: '#FEF2F2', border: 'rgba(220,38,38,0.18)', label: 'CRITIQUE', textColor: '#7F1D1D' },
  high:     { color: '#EA580C', bg: '#FFF7ED', border: 'rgba(234,88,12,0.18)', label: 'HAUTE', textColor: '#9A3412' },
  medium:   { color: '#D97706', bg: '#FFFBEB', border: 'rgba(217,119,6,0.18)', label: 'MODÉRÉE', textColor: '#92400E' },
  low:      { color: '#059669', bg: '#ECFDF5', border: 'rgba(5,150,105,0.18)', label: 'FAIBLE', textColor: '#065F46' },
};

function ImpactBar({ score }: { score: number }) {
  const abs = Math.abs(score);
  const color = score < -0.4 ? '#DC2626' : score < 0 ? '#EA580C' : score > 0.4 ? '#059669' : '#D97706';
  const bg = score < -0.4 ? '#FEF2F2' : score < 0 ? '#FFF7ED' : score > 0.4 ? '#ECFDF5' : '#FFFBEB';
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(abs * 100)}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ background: color, [score < 0 ? 'right' : 'left']: 0 }}
        />
      </div>
      <span className="text-sm font-mono font-semibold px-2 py-0.5 rounded-lg" style={{ color, background: bg }}>
        {score >= 0 ? '+' : ''}{score.toFixed(2)}
      </span>
    </div>
  );
}

function AlertCard({ alert }: { alert: MarketAlert }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = LEVEL_CONFIG[alert.level] ?? LEVEL_CONFIG.low;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl overflow-hidden"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <div className="flex items-start gap-3 p-5">
        <div
          className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
          style={{ background: `${cfg.color}12`, color: cfg.color }}
        >
          <ShieldAlert size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-[11px] font-bold px-2.5 py-1 rounded-full" style={{ background: `${cfg.color}12`, color: cfg.color }}>
              {cfg.label}
            </span>
            <span className="text-xs font-medium" style={{ color: 'var(--text-faint)' }}>
              {new Date(alert.generated_at).toLocaleString('fr-FR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          </div>
          <p className="text-base font-semibold leading-snug" style={{ color: cfg.textColor }}>
            {alert.title}
          </p>
          {alert.summary && (
            <p className="text-sm leading-relaxed mt-1.5 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
              {alert.summary}
            </p>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 p-2 rounded-xl transition-all"
          style={{ color: 'var(--text-faint)' }}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      <div className="px-5 pb-4">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
            Impact sur Talan
          </span>
          {alert.talan_impact_score < 0
            ? <TrendingDown size={12} style={{ color: '#DC2626' }} />
            : alert.talan_impact_score > 0
            ? <TrendingUp size={12} style={{ color: '#059669' }} />
            : <Minus size={12} style={{ color: 'var(--text-faint)' }} />}
        </div>
        <ImpactBar score={alert.talan_impact_score} />
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 space-y-4" style={{ borderTop: `1px solid ${cfg.border}` }}>
              {alert.affected_entities?.length > 0 && (
                <div className="pt-4">
                  <p className="text-xs font-bold mb-2" style={{ color: 'var(--text-muted)' }}>
                    Entités affectées
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {alert.affected_entities.map((e) => (
                      <span
                        key={e}
                        className="px-2.5 py-1 rounded-full text-xs font-medium"
                        style={{
                          background: 'var(--bg-surface)',
                          border: '1px solid var(--border-subtle)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {e}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {alert.talan_recommended_action && (
                <div className="flex items-start gap-2.5 p-3.5 rounded-2xl" style={{ background: 'var(--primary-subtle)', border: '1px solid var(--primary-muted)' }}>
                  <Eye size={13} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--primary)' }} />
                  <p className="text-sm leading-relaxed" style={{ color: 'var(--primary-dark)' }}>
                    {alert.talan_recommended_action}
                  </p>
                </div>
              )}

              {alert.gnn_hidden_risks?.length > 0 && (
                <div>
                  <p className="text-xs font-bold mb-1.5" style={{ color: 'var(--text-muted)' }}>
                    Risques cachés GNN
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {alert.gnn_hidden_risks.map((r) => (
                      <span
                        key={r}
                        className="px-2.5 py-1 rounded-full text-xs font-semibold"
                        style={{ background: '#F5F3FF', color: '#6D28D9', border: '1px solid #DDD6FE' }}
                      >
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
          <div key={i} className="h-28 rounded-2xl animate-pulse" style={{ background: 'var(--border-subtle)' }} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 flex-wrap">
        {levels.map((lv) => {
          const cfg = lv === 'all' ? null : LEVEL_CONFIG[lv];
          const count = lv === 'all' ? alerts.length : alerts.filter((a) => a.level === lv).length;
          const isActive = filter === lv;
          return (
            <button
              key={lv}
              onClick={() => setFilter(lv)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold transition-all"
              style={{
                background: isActive ? (cfg ? cfg.bg : 'var(--primary-subtle)') : 'transparent',
                color: isActive ? (cfg ? cfg.color : 'var(--primary-dark)') : 'var(--text-faint)',
                border: `1px solid ${isActive ? (cfg ? cfg.border : 'var(--primary-muted)') : 'transparent'}`,
              }}
            >
              {lv === 'all' ? 'Toutes' : LEVEL_CONFIG[lv].label}
              <span className="opacity-60">{count}</span>
            </button>
          );
        })}
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <ShieldAlert size={34} style={{ color: 'var(--text-faint)' }} />
          <p className="text-base font-semibold" style={{ color: 'var(--text-faint)' }}>
            Aucune alerte
          </p>
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
