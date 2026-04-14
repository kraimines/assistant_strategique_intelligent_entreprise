import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import type { RadarScores } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  scores: RadarScores;
  threatLevel: number;
  threatLabel: string;
}

const AXIS_LABELS: Record<keyof RadarScores, string> = {
  IA_Générative: 'IA',
  Cloud: 'Cloud',
  Recrutement: 'Recrutement',
  Partenariats: 'Partenariats',
  Innovation_Produit: 'Innovation',
};

const tooltipStyle = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  border: '1px solid var(--chart-tooltip-border)',
  borderRadius: '12px',
  color: 'var(--chart-tooltip-color)',
  fontSize: '12px',
};

function ThreatBadge({ level, label }: { level: number; label: string }) {
  const pct = Math.round(level * 100);
  const color =
    pct >= 75 ? '#ef4444'
    : pct >= 50 ? '#f97316'
    : pct >= 25 ? '#eab308'
    : '#22c55e';
  const emoji = pct >= 75 ? '🔴' : pct >= 50 ? '🟠' : pct >= 25 ? '🟡' : '🟢';

  return (
    <div className="flex items-center gap-3">
      <span className="text-white/60 text-xs">Niveau de menace</span>
      <span className="text-sm font-bold" style={{ color }}>
        {emoji} {label} ({pct}%)
      </span>
    </div>
  );
}

export default function ThreatRadar({ scores, threatLevel, threatLabel }: Props) {
  const data = (Object.keys(scores) as (keyof RadarScores)[]).map((key) => ({
    axis: AXIS_LABELS[key],
    value: scores[key],
    fullMark: 100,
  }));

  return (
    <GlassCard animate className="p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold text-sm">Radar des menaces</h3>
        <ThreatBadge level={threatLevel} label={threatLabel} />
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
          <PolarGrid stroke="rgba(255,255,255,0.08)" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fill: 'rgba(255,255,255,0.55)', fontSize: 11 }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 9 }}
            axisLine={false}
          />
          <Radar
            name="Score"
            dataKey="value"
            stroke="#00d4ff"
            fill="#00d4ff"
            fillOpacity={0.18}
            strokeWidth={2}
            dot={{ fill: '#00d4ff', r: 3 }}
          />
          <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v}/100`, 'Score']} />
        </RadarChart>
      </ResponsiveContainer>

      {/* Axis scores table */}
      <div className="grid grid-cols-5 gap-2 pt-1 border-t border-white/6">
        {(Object.entries(scores) as [keyof RadarScores, number][]).map(([key, val]) => (
          <div key={key} className="flex flex-col items-center gap-1">
            <span className="text-white/40 text-[10px] text-center leading-tight">
              {AXIS_LABELS[key]}
            </span>
            <span
              className="text-sm font-bold font-mono"
              style={{
                color: val >= 70 ? '#ef4444' : val >= 40 ? '#f97316' : '#22c55e',
              }}
            >
              {val}
            </span>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
