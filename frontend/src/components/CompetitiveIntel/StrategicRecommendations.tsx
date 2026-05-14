import { AlertTriangle, ArrowRight, CheckCircle, Info } from 'lucide-react';
import { motion } from 'framer-motion';
import type { KeyMove, RecommendedAction } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  recommendations: RecommendedAction[];
  keyMoves: KeyMove[];
  summary: string;
}

const PRIORITY_CONFIG = {
  haute: {
    icon: AlertTriangle,
    color: '#DC2626',
    bg: '#FEF2F2',
    border: 'rgba(220,38,38,0.18)',
    textColor: '#7F1D1D',
    label: 'Haute priorité',
  },
  moyenne: {
    icon: ArrowRight,
    color: '#EA580C',
    bg: '#FFF7ED',
    border: 'rgba(234,88,12,0.18)',
    textColor: '#9A3412',
    label: 'Moyenne priorité',
  },
  basse: {
    icon: CheckCircle,
    color: '#059669',
    bg: '#ECFDF5',
    border: 'rgba(5,150,105,0.18)',
    textColor: '#065F46',
    label: 'Basse priorité',
  },
};

function parseDate(raw: string): string {
  if (!raw) return '';
  try {
    return new Date(raw).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
  } catch {
    return raw.slice(0, 10);
  }
}

export default function StrategicRecommendations({ recommendations, keyMoves, summary }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <GlassCard animate className="p-4">
        <div className="flex items-start gap-3">
          <Info size={16} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--primary)' }} />
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {summary}
          </p>
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GlassCard animate className="p-5 flex flex-col gap-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            Recommandations stratégiques
          </h3>
          {recommendations.map((rec, i) => {
            const cfg = PRIORITY_CONFIG[rec.priority] ?? PRIORITY_CONFIG.basse;
            const Icon = cfg.icon;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                className="flex items-start gap-3 p-3.5 rounded-2xl"
                style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
              >
                <Icon size={15} style={{ color: cfg.color }} className="flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-snug font-medium" style={{ color: cfg.textColor }}>
                    {rec.action}
                  </p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ color: cfg.color, background: `${cfg.color}14` }}>
                      {cfg.label}
                    </span>
                    {rec.axis && (
                      <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                        {rec.axis}
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </GlassCard>

        <GlassCard animate className="p-5 flex flex-col gap-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            Mouvements détectés
          </h3>
          {keyMoves.length === 0 ? (
            <p className="text-sm py-4 text-center font-medium" style={{ color: 'var(--text-faint)' }}>
              Aucun mouvement significatif détecté.
            </p>
          ) : (
            keyMoves.slice(0, 6).map((move, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
                className="flex items-start gap-3 p-3.5 rounded-2xl transition-all"
                style={{ background: 'var(--bg-base)', border: '1px solid var(--border-subtle)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-strong)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-subtle)';
                }}
              >
                <div className="w-2 h-2 rounded-full flex-shrink-0 mt-1.5" style={{ background: 'var(--primary)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-snug font-medium line-clamp-2" style={{ color: 'var(--text-primary)' }}>
                    {move.move}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className="text-xs font-bold" style={{ color: 'var(--primary)' }}>
                      {move.company}
                    </span>
                    {move.date && (
                      <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                        {parseDate(move.date)}
                      </span>
                    )}
                    {move.source && (
                      <span className="text-xs ml-auto" style={{ color: 'var(--text-faint)' }}>
                        {move.source}
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </GlassCard>
      </div>
    </div>
  );
}
