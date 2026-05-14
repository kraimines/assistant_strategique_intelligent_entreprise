import { motion } from 'framer-motion';
import { Clock, Target, TrendingUp, Zap, AlertTriangle } from 'lucide-react';
import type { AnticipatedMove } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  anticipatedMoves: AnticipatedMove[];
  hiringSignals: string[];
  companies: string[];
}

const AXIS_ICONS: Record<string, React.ReactNode> = {
  IA_Générative: <Zap size={15} />,
  Cloud: <TrendingUp size={15} />,
  Recrutement: <Target size={15} />,
  Partenariats: <AlertTriangle size={15} />,
  Innovation_Produit: <TrendingUp size={15} />,
};

const HORIZON_CFG: Record<string, { color: string; bg: string; border: string; textColor: string }> = {
  '1–3 mois': { color: '#DC2626', bg: '#FEF2F2', border: 'rgba(220,38,38,0.18)', textColor: '#7F1D1D' },
  '3–6 mois': { color: '#EA580C', bg: '#FFF7ED', border: 'rgba(234,88,12,0.18)', textColor: '#9A3412' },
  '6–12 mois': { color: '#D97706', bg: '#FFFBEB', border: 'rgba(217,119,6,0.18)', textColor: '#92400E' },
  '3–9 mois': { color: '#D97706', bg: '#FFFBEB', border: 'rgba(217,119,6,0.18)', textColor: '#92400E' },
};
const HORIZON_DEFAULT = HORIZON_CFG['3–6 mois'];

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 70 ? '#DC2626' : value >= 40 ? '#EA580C' : '#D97706';
  const bg = value >= 70 ? '#FEF2F2' : value >= 40 ? '#FFF7ED' : '#FFFBEB';
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
      <span className="text-sm font-bold font-mono px-2 py-0.5 rounded-lg" style={{ color, background: bg }}>
        {value}%
      </span>
    </div>
  );
}

export default function AnticipationPanel({ anticipatedMoves, hiringSignals, companies }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: '#F5F3FF', border: '1px solid #DDD6FE' }}>
          <Clock size={17} style={{ color: '#7C3AED' }} />
        </div>
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            Anticipation stratégique
          </h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            Mouvements probables de {companies.join(', ')} dans les prochains mois
          </p>
        </div>
      </div>

      {anticipatedMoves.length === 0 ? (
        <GlassCard animate className="p-10 flex flex-col items-center gap-3">
          <Clock size={30} style={{ color: 'var(--text-faint)' }} />
          <p className="text-sm text-center font-medium" style={{ color: 'var(--text-muted)' }}>
            Données insuffisantes pour établir des prédictions.<br />
            Relancez l'analyse avec plus de sources.
          </p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {anticipatedMoves.map((move, i) => {
            const hc = HORIZON_CFG[move.horizon] ?? HORIZON_DEFAULT;
            const icon = AXIS_ICONS[move.axis] ?? <Target size={15} />;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                <div className="p-4 rounded-2xl flex flex-col gap-3" style={{ background: hc.bg, border: `1px solid ${hc.border}`, boxShadow: 'var(--shadow-card)' }}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold" style={{ color: hc.color, background: `${hc.color}14` }}>
                      <Clock size={11} />
                      {move.horizon}
                    </div>
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${hc.color}14`, color: hc.color }}>
                      {icon}
                    </div>
                  </div>

                  <p className="text-sm font-semibold leading-snug" style={{ color: hc.textColor }}>
                    {move.prediction}
                  </p>

                  <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    {move.rationale}
                  </p>

                  <div className="pt-2" style={{ borderTop: `1px solid ${hc.border}` }}>
                    <p className="text-xs font-semibold mb-1.5" style={{ color: 'var(--text-muted)' }}>
                      Confiance
                    </p>
                    <ConfidenceBar value={move.confidence} />
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {hiringSignals.length > 0 && (
        <GlassCard animate className="p-4">
          <p className="text-sm font-bold mb-3" style={{ color: 'var(--text-secondary)' }}>
            Signaux détectés dans la presse
          </p>
          <div className="flex flex-col gap-2">
            {hiringSignals.slice(0, 5).map((signal, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
                className="flex items-start gap-2.5"
              >
                <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5" style={{ background: 'var(--primary)' }} />
                <span className="text-sm leading-snug" style={{ color: 'var(--text-secondary)' }}>
                  {signal}
                </span>
              </motion.div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
