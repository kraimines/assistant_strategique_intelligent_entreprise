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
    color: '#ef4444',
    bg: 'bg-red-500/8',
    border: 'border-red-500/25',
    label: 'Haute priorité',
  },
  moyenne: {
    icon: ArrowRight,
    color: '#f97316',
    bg: 'bg-orange-500/8',
    border: 'border-orange-500/25',
    label: 'Moyenne priorité',
  },
  basse: {
    icon: CheckCircle,
    color: '#22c55e',
    bg: 'bg-emerald-500/8',
    border: 'border-emerald-500/25',
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
      {/* Summary banner */}
      <GlassCard animate className="p-4">
        <div className="flex items-start gap-3">
          <Info size={15} className="text-cyber-cyan flex-shrink-0 mt-0.5" />
          <p className="text-white/70 text-xs leading-relaxed">{summary}</p>
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recommendations */}
        <GlassCard animate className="p-5 flex flex-col gap-3">
          <h3 className="text-white font-semibold text-sm">Recommandations stratégiques</h3>
          {recommendations.map((rec, i) => {
            const cfg = PRIORITY_CONFIG[rec.priority] ?? PRIORITY_CONFIG.basse;
            const Icon = cfg.icon;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07 }}
                className={`flex items-start gap-3 p-3 rounded-xl border ${cfg.bg} ${cfg.border}`}
              >
                <Icon size={14} style={{ color: cfg.color }} className="flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-white/85 text-xs leading-snug">{rec.action}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                      style={{
                        color: cfg.color,
                        background: `${cfg.color}18`,
                      }}
                    >
                      {cfg.label}
                    </span>
                    <span className="text-white/30 text-[10px]">{rec.axis}</span>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </GlassCard>

        {/* Key moves */}
        <GlassCard animate className="p-5 flex flex-col gap-3">
          <h3 className="text-white font-semibold text-sm">Mouvements détectés</h3>
          {keyMoves.length === 0 ? (
            <p className="text-white/30 text-xs py-4 text-center">
              Aucun mouvement significatif détecté.
            </p>
          ) : (
            keyMoves.slice(0, 6).map((move, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
                className="flex items-start gap-3 p-3 rounded-xl bg-white/3 border border-white/6 hover:border-white/10 transition-all"
              >
                <div className="w-1 h-1 rounded-full bg-cyber-cyan flex-shrink-0 mt-1.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-white/80 text-xs leading-snug line-clamp-2">{move.move}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-cyber-cyan/70 text-[10px] font-medium">{move.company}</span>
                    {move.date && (
                      <span className="text-white/25 text-[10px]">{parseDate(move.date)}</span>
                    )}
                    {move.source && (
                      <span className="text-white/20 text-[10px] ml-auto">{move.source}</span>
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
