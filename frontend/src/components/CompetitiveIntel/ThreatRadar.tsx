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

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-surface)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '12px',
  color: 'var(--text-primary)',
  fontSize: '13px',
};

function ThreatBadge({ level, label }: { level: number; label: string }) {
  const pct = Math.round(level * 100);
  const color = pct >= 75 ? '#DC2626' : pct >= 50 ? '#EA580C' : pct >= 25 ? '#D97706' : '#059669';
  const bg = pct >= 75 ? '#FEF2F2' : pct >= 50 ? '#FFF7ED' : pct >= 25 ? '#FFFBEB' : '#ECFDF5';
  const border = pct >= 75 ? 'rgba(220,38,38,0.18)' : pct >= 50 ? 'rgba(234,88,12,0.18)' : pct >= 25 ? 'rgba(217,119,6,0.18)' : 'rgba(5,150,105,0.18)';
  const emoji = pct >= 75 ? '🔴' : pct >= 50 ? '🟠' : pct >= 25 ? '🟡' : '🟢';

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold" style={{ background: bg, border: `1px solid ${border}`, color }}>
      <span>{emoji}</span>
      <span>{label} ({pct}%)</span>
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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          Radar des menaces
        </h3>
        <ThreatBadge level={threatLevel} label={threatLabel} />
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
          <PolarGrid stroke="rgba(148,163,184,0.18)" />
          <PolarAngleAxis dataKey="axis" tick={{ fill: '#475569', fontSize: 12, fontWeight: 600 }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#94A3B8', fontSize: 10 }} axisLine={false} />
          <Radar
            name="Score"
            dataKey="value"
            stroke="#3B82F6"
            fill="#3B82F6"
            fillOpacity={0.16}
            strokeWidth={2}
            dot={{ fill: '#3B82F6', r: 3.5, strokeWidth: 0 }}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => [`${v}/100`, 'Score']} />
        </RadarChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-5 gap-2 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {(Object.entries(scores) as [keyof RadarScores, number][]).map(([key, val]) => {
          const color = val >= 70 ? '#DC2626' : val >= 40 ? '#EA580C' : '#059669';
          const bg = val >= 70 ? '#FEF2F2' : val >= 40 ? '#FFF7ED' : '#ECFDF5';
          return (
            <div key={key} className="flex flex-col items-center gap-1.5">
              <span className="text-xs font-semibold text-center leading-tight" style={{ color: 'var(--text-muted)' }}>
                {AXIS_LABELS[key]}
              </span>
              <span className="text-sm font-bold font-mono px-2 py-0.5 rounded-lg" style={{ color, background: bg }}>
                {val}
              </span>
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}
