import { motion } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import type { KPI } from '../../types';

interface KPICardProps extends KPI {
  icon?: React.ReactNode;
  delay?: number;
}

const colorMap: Record<string, { accent: string; grad: string; glow: string }> = {
  cyan:    { accent: '#0ea5e9', grad: 'linear-gradient(135deg,#0ea5e9,#38bdf8)', glow: 'rgba(14,165,233,0.22)' },
  violet:  { accent: '#7c3aed', grad: 'linear-gradient(135deg,#7c3aed,#a78bfa)', glow: 'rgba(124,58,237,0.22)' },
  emerald: { accent: '#059669', grad: 'linear-gradient(135deg,#059669,#34d399)', glow: 'rgba(5,150,105,0.22)' },
  amber:   { accent: '#d97706', grad: 'linear-gradient(135deg,#d97706,#fbbf24)', glow: 'rgba(217,119,6,0.22)'  },
  pink:    { accent: '#db2777', grad: 'linear-gradient(135deg,#db2777,#f472b6)', glow: 'rgba(219,39,119,0.22)' },
  teal:    { accent: '#0d9488', grad: 'linear-gradient(135deg,#0d9488,#2dd4bf)', glow: 'rgba(13,148,136,0.22)' },
};

export default function KPICard({ label, value, trend, unit, color = 'cyan', icon, delay = 0 }: KPICardProps) {
  const c = colorMap[color] ?? colorMap.cyan;

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: 'easeOut' }}
      className="relative rounded-[18px] p-5 overflow-hidden cursor-default"
      style={{
        background: 'rgba(255,255,255,0.90)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(255,255,255,0.70)',
        boxShadow: `0 4px 24px ${c.glow}, 0 1px 4px rgba(0,0,0,0.06)`,
      }}
      whileHover={{ y: -3, boxShadow: `0 12px 40px ${c.glow}` }}
    >
      <div className="absolute top-0 left-0 right-0 h-1 rounded-t-[18px]" style={{ background: c.grad }} />

      <div className="flex items-start justify-between mt-1">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: '#64748b' }}>
            {label}
          </p>
          <div className="flex items-baseline gap-1.5 mb-2">
            <span className="text-[2rem] font-bold leading-none" style={{ color: c.accent }}>
              {value}
            </span>
            {unit && <span className="text-sm font-medium" style={{ color: '#64748b' }}>{unit}</span>}
          </div>
          {trend !== undefined && (
            trend > 0 ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full w-fit"
                style={{ background: 'rgba(16,185,129,0.15)', color: '#059669' }}>
                <ArrowUpRight size={11} /> +{trend}%
              </span>
            ) : trend < 0 ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full w-fit"
                style={{ background: 'rgba(239,68,68,0.12)', color: '#dc2626' }}>
                <ArrowDownRight size={11} /> {trend}%
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full w-fit"
                style={{ background: 'rgba(100,116,139,0.12)', color: '#64748b' }}>
                <Minus size={11} /> 0%
              </span>
            )
          )}
        </div>
        {icon && (
          <div className="w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0 ml-3"
            style={{ background: `${c.accent}18`, color: c.accent }}>
            {icon}
          </div>
        )}
      </div>
    </motion.div>
  );
}
