import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { Briefcase, TrendingUp } from 'lucide-react';
import { motion } from 'framer-motion';
import type { JobsData } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props { jobsData: JobsData }

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  border:          '1px solid var(--chart-tooltip-border)',
  borderRadius:    '12px',
  color:           'var(--chart-tooltip-color)',
  fontSize:        '13px',
};

/* Cold-palette bar colors */
const BAR_COLORS = [
  '#3B82F6', '#14B8A6', '#8B5CF6', '#10B981', '#F59E0B',
  '#60A5FA', '#2DD4BF', '#A78BFA', '#34D399', '#FCD34D',
];

export default function JobSignalsChart({ jobsData }: Props) {
  const chartData = jobsData.top_skills_recruited.slice(0, 10).map((s) => ({
    name:  s.skill,
    count: s.count,
  }));

  return (
    <GlassCard animate className="p-5 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <Briefcase size={17} style={{ color: 'var(--primary)' }} />
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            Signaux recrutement
            <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-muted)' }}>
              — {jobsData.company}
            </span>
          </h3>
        </div>
        <span
          className="text-sm font-semibold px-3 py-1 rounded-full"
          style={{ background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' }}
        >
          {jobsData.total_jobs_found} offres
        </span>
      </div>

      {/* Strategic signals */}
      {jobsData.strategic_signals.length > 0 && (
        <div className="flex flex-col gap-2">
          {jobsData.strategic_signals.map((signal, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08 }}
              className="flex items-start gap-2.5 p-3 rounded-xl"
              style={{
                background: 'var(--warning-subtle)',
                border:     '1px solid rgba(245,158,11,0.25)',
              }}
            >
              <TrendingUp size={14} className="flex-shrink-0 mt-0.5" style={{ color: '#D97706' }} />
              <span className="text-sm leading-snug font-medium" style={{ color: '#92400E' }}>
                {signal}
              </span>
            </motion.div>
          ))}
        </div>
      )}

      {/* Bar chart */}
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 16, bottom: 0, left: 90 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(15,23,42,0.06)"
              horizontal={false}
            />
            <XAxis
              type="number"
              tick={{ fill: '#94A3B8', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: '#475569', fontSize: 12, fontWeight: 500 }}
              axisLine={false}
              tickLine={false}
              width={88}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v: number) => [v, 'Occurrences']}
            />
            <Bar dataKey="count" radius={[0, 5, 5, 0]} maxBarSize={16}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-sm text-center py-8 font-medium" style={{ color: 'var(--text-faint)' }}>
          Aucune offre d'emploi trouvée.
        </p>
      )}
    </GlassCard>
  );
}
