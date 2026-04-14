import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { Briefcase, TrendingUp } from 'lucide-react';
import { motion } from 'framer-motion';
import type { JobsData } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  jobsData: JobsData;
}

const tooltipStyle = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  border: '1px solid var(--chart-tooltip-border)',
  borderRadius: '12px',
  color: 'var(--chart-tooltip-color)',
  fontSize: '12px',
};

const BAR_COLORS = [
  '#00d4ff', '#7c3aed', '#f97316', '#22c55e', '#e879f9',
  '#38bdf8', '#a78bfa', '#fb923c', '#4ade80', '#f0abfc',
];

export default function JobSignalsChart({ jobsData }: Props) {
  const chartData = jobsData.top_skills_recruited.slice(0, 10).map((s) => ({
    name: s.skill,
    count: s.count,
  }));

  return (
    <GlassCard animate className="p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Briefcase size={15} className="text-cyber-cyan" />
          <h3 className="text-white font-semibold text-sm">
            Signaux recrutement
            <span className="ml-2 text-white/40 font-normal text-xs">
              — {jobsData.company}
            </span>
          </h3>
        </div>
        <span className="text-white/40 text-xs font-mono">
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
              className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/8 border border-amber-500/20"
            >
              <TrendingUp size={13} className="text-amber-400 flex-shrink-0 mt-0.5" />
              <span className="text-amber-300 text-xs leading-snug">{signal}</span>
            </motion.div>
          ))}
        </div>
      )}

      {/* Bar chart — top skills */}
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 16, bottom: 0, left: 80 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={78}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(v: number) => [v, 'Occurrences']}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={14}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-white/30 text-sm text-center py-8">
          Aucune offre d'emploi trouvée.
        </p>
      )}
    </GlassCard>
  );
}
