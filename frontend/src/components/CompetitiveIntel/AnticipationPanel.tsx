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
  IA_Générative: <Zap size={14} />,
  Cloud: <TrendingUp size={14} />,
  Recrutement: <Target size={14} />,
  Partenariats: <AlertTriangle size={14} />,
  Innovation_Produit: <TrendingUp size={14} />,
};

const HORIZON_COLOR: Record<string, { color: string; bg: string; border: string }> = {
  '1–3 mois':  { color: '#ef4444', bg: 'bg-red-500/8',    border: 'border-red-500/25' },
  '3–6 mois':  { color: '#f97316', bg: 'bg-orange-500/8', border: 'border-orange-500/25' },
  '6–12 mois': { color: '#eab308', bg: 'bg-yellow-500/8', border: 'border-yellow-500/20' },
  '3–9 mois':  { color: '#eab308', bg: 'bg-yellow-500/8', border: 'border-yellow-500/20' },
};

function confidenceBar(value: number) {
  const color = value >= 70 ? '#ef4444' : value >= 40 ? '#f97316' : '#eab308';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 rounded-full bg-white/8 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="h-full rounded-full"
          style={{ background: color, boxShadow: `0 0 6px ${color}60` }}
        />
      </div>
      <span className="text-[10px] font-mono" style={{ color }}>{value}%</span>
    </div>
  );
}

export default function AnticipationPanel({ anticipatedMoves, hiringSignals, companies }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-cyber-violet/20 border border-cyber-violet/30 flex items-center justify-center">
          <Clock size={14} className="text-cyber-violet" />
        </div>
        <div>
          <h2 className="text-white font-semibold text-sm">
            Anticipation stratégique
          </h2>
          <p className="text-white/40 text-xs">
            Mouvements probables de {companies.join(', ')} dans les prochains mois
          </p>
        </div>
      </div>

      {anticipatedMoves.length === 0 ? (
        <GlassCard animate className="p-8 flex flex-col items-center gap-3">
          <Clock size={28} className="text-white/15" />
          <p className="text-white/30 text-sm text-center">
            Données insuffisantes pour établir des prédictions.<br />
            Relancez l'analyse avec plus de sources.
          </p>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {anticipatedMoves.map((move, i) => {
            const hc = HORIZON_COLOR[move.horizon] ?? HORIZON_COLOR['3–6 mois'];
            const icon = AXIS_ICONS[move.axis] ?? <Target size={14} />;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                <GlassCard className={`p-4 flex flex-col gap-3 border ${hc.border} ${hc.bg}`}>
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2">
                    <div
                      className="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-medium"
                      style={{ color: hc.color, background: `${hc.color}18` }}
                    >
                      <Clock size={10} />
                      {move.horizon}
                    </div>
                    <div
                      className="w-6 h-6 rounded-lg flex items-center justify-center"
                      style={{ background: `${hc.color}18`, color: hc.color }}
                    >
                      {icon}
                    </div>
                  </div>

                  {/* Prediction */}
                  <p className="text-white font-medium text-sm leading-snug">
                    {move.prediction}
                  </p>

                  {/* Rationale */}
                  <p className="text-white/45 text-[11px] leading-relaxed">
                    {move.rationale}
                  </p>

                  {/* Confidence */}
                  <div className="pt-1 border-t border-white/6">
                    <p className="text-white/30 text-[10px] mb-1">Confiance</p>
                    {confidenceBar(move.confidence)}
                  </div>
                </GlassCard>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Hiring signals */}
      {hiringSignals.length > 0 && (
        <GlassCard animate className="p-4">
          <p className="text-white/50 text-xs font-medium mb-3">
            Signaux détectés dans la presse
          </p>
          <div className="flex flex-col gap-2">
            {hiringSignals.slice(0, 5).map((signal, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
                className="flex items-start gap-2 text-xs"
              >
                <div className="w-1 h-1 rounded-full bg-cyber-cyan flex-shrink-0 mt-1.5" />
                <span className="text-white/65 leading-snug">{signal}</span>
              </motion.div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
