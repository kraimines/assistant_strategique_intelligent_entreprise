import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { KPI } from '../../types';

interface KPICardProps extends KPI {
  icon?: React.ReactNode;
  delay?: number;
}

const colorMap = {
  cyan: {
    bg: 'bg-cyber-cyan/10',
    border: 'border-cyber-cyan/20',
    text: 'text-cyber-cyan',
    glow: '0 0 20px rgba(0,212,255,0.12)',
    iconBg: 'bg-cyber-cyan/15',
  },
  violet: {
    bg: 'bg-cyber-violet/10',
    border: 'border-cyber-violet/20',
    text: 'text-cyber-violet',
    glow: '0 0 20px rgba(124,58,237,0.12)',
    iconBg: 'bg-cyber-violet/15',
  },
  emerald: {
    bg: 'bg-cyber-emerald/10',
    border: 'border-cyber-emerald/20',
    text: 'text-cyber-emerald',
    glow: '0 0 20px rgba(16,185,129,0.12)',
    iconBg: 'bg-cyber-emerald/15',
  },
  amber: {
    bg: 'bg-cyber-amber/10',
    border: 'border-cyber-amber/20',
    text: 'text-cyber-amber',
    glow: '0 0 20px rgba(245,158,11,0.12)',
    iconBg: 'bg-cyber-amber/15',
  },
  pink: {
    bg: 'bg-cyber-pink/10',
    border: 'border-cyber-pink/20',
    text: 'text-cyber-pink',
    glow: '0 0 20px rgba(236,72,153,0.12)',
    iconBg: 'bg-cyber-pink/15',
  },
};

export default function KPICard({ label, value, trend, unit, color = 'cyan', icon, delay = 0 }: KPICardProps) {
  const c = colorMap[color];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      className={`
        rounded-2xl p-5 border ${c.border}
        transition-all duration-300 hover:scale-[1.02]
      `}
      style={{
        background: 'rgba(12, 12, 20, 0.7)',
        backdropFilter: 'blur(20px)',
        boxShadow: c.glow,
      }}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">{label}</p>
          <div className="flex items-baseline gap-1.5">
            <span className={`text-3xl font-bold ${c.text}`}>{value}</span>
            {unit && <span className="text-white/40 text-sm">{unit}</span>}
          </div>
          {trend !== undefined && (
            <div className="flex items-center gap-1 mt-2">
              {trend > 0 ? (
                <TrendingUp size={13} className="text-cyber-emerald" />
              ) : trend < 0 ? (
                <TrendingDown size={13} className="text-red-400" />
              ) : (
                <Minus size={13} className="text-white/30" />
              )}
              <span className={`text-xs font-medium ${trend > 0 ? 'text-cyber-emerald' : trend < 0 ? 'text-red-400' : 'text-white/30'}`}>
                {trend > 0 ? '+' : ''}{trend}%
              </span>
              <span className="text-white/30 text-xs">vs mois dernier</span>
            </div>
          )}
        </div>
        {icon && (
          <div className={`w-10 h-10 rounded-xl ${c.iconBg} flex items-center justify-center flex-shrink-0 ml-3`}>
            {icon}
          </div>
        )}
      </div>
    </motion.div>
  );
}
