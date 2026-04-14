/**
 * GNNPredictions — displays GNN inference results.
 * Sections:
 *  - Talan prediction gauge + systemic risk
 *  - Bar chart of all company predictions (Recharts)
 *  - Hidden risks ranked list
 */
import { motion } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer,
} from 'recharts';
import { Brain, ShieldAlert, TrendingDown, TrendingUp, Minus, Zap } from 'lucide-react';
import type { GNNResult } from '../../api/marketAnalysisApi';

interface Props {
  result: GNNResult | undefined;
  loading: boolean;
  onRunGNN: () => void;
  running: boolean;
}

// ── Radial gauge ──────────────────────────────────────────────────────────────
function RadialGauge({ value, label, color }: { value: number; label: string; color: string }) {
  const norm = (value + 1) / 2; // map [-1,1] → [0,1]
  const angle = norm * 180 - 90; // sweep 180° from -90° to +90°
  const r = 52;
  const cx = 70; const cy = 70;
  // Arc path (semicircle)
  const arcStart = (x: number, y: number) => `${cx + r * Math.cos(((x - 90) * Math.PI) / 180)} ${cy + r * Math.sin(((x - 90) * Math.PI) / 180)}`;
  const trackArc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative">
        <svg width={140} height={80} viewBox="0 0 140 80">
          {/* Track */}
          <path d={trackArc} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={8} strokeLinecap="round" />
          {/* Value arc */}
          <motion.path
            d={trackArc}
            fill="none"
            stroke={color}
            strokeWidth={8}
            strokeLinecap="round"
            strokeDasharray={`${r * Math.PI}`}
            initial={{ strokeDashoffset: r * Math.PI }}
            animate={{ strokeDashoffset: r * Math.PI * (1 - norm) }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ transformOrigin: '50% 50%' }}
          />
          {/* Needle */}
          <motion.line
            x1={cx} y1={cy}
            x2={cx + (r - 10) * Math.cos(((angle - 90) * Math.PI) / 180)}
            y2={cy + (r - 10) * Math.sin(((angle - 90) * Math.PI) / 180)}
            stroke={color}
            strokeWidth={2}
            strokeLinecap="round"
            initial={{ rotate: -90 }}
            animate={{ rotate: angle }}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          />
          {/* Center dot */}
          <circle cx={cx} cy={cy} r={4} fill={color} />
          {/* Value text */}
          <text x={cx} y={cy - 12} textAnchor="middle" fontSize="14" fontWeight="700" fill={color}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </text>
        </svg>
      </div>
      <p className="text-[10px] text-white/40 text-center leading-tight">{label}</p>
    </div>
  );
}

// ── Systemic risk ring ────────────────────────────────────────────────────────
function RiskRing({ value }: { value: number }) {
  const color = value >= 0.7 ? '#ef4444' : value >= 0.4 ? '#f97316' : value >= 0.2 ? '#f59e0b' : '#10b981';
  const label = value >= 0.7 ? 'CRITIQUE' : value >= 0.4 ? 'ÉLEVÉ' : value >= 0.2 ? 'MODÉRÉ' : 'FAIBLE';
  const r = 34; const circ = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-20 h-20 flex items-center justify-center">
        <svg className="absolute inset-0" width={80} height={80} viewBox="0 0 80 80">
          <circle cx={40} cy={40} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={7} />
          <motion.circle
            cx={40} cy={40} r={r}
            fill="none"
            stroke={color}
            strokeWidth={7}
            strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ * (1 - value) }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ transformOrigin: '50% 50%', transform: 'rotate(-90deg)' }}
          />
        </svg>
        <div className="text-center z-10">
          <p className="text-sm font-bold" style={{ color }}>{Math.round(value * 100)}%</p>
        </div>
      </div>
      <div className="text-center">
        <p className="text-[10px] font-bold" style={{ color }}>{label}</p>
        <p className="text-[9px] text-white/30">Risque systémique</p>
      </div>
    </div>
  );
}

// ── Custom tooltip for bar chart ──────────────────────────────────────────────
function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const score = d.predicted_impact;
  const color = score < -0.3 ? '#ef4444' : score > 0.3 ? '#10b981' : '#f59e0b';
  return (
    <div className="rounded-xl p-3 text-xs shadow-2xl"
      style={{ background: 'rgba(12,12,20,0.96)', border: '1px solid rgba(255,255,255,0.12)' }}>
      <p className="font-semibold text-white/85 mb-1">{d.entity_name}</p>
      <p style={{ color }}>Impact: {score >= 0 ? '+' : ''}{score.toFixed(3)}</p>
      <p className="text-white/40">Confiance: {Math.round(d.confidence * 100)}%</p>
      <p className="text-white/40">Sauts: {d.propagation_hops}</p>
      {d.hidden_risk && <p className="text-violet-400 mt-1">⚡ Risque caché</p>}
    </div>
  );
}

export default function GNNPredictions({ result, loading, onRunGNN, running }: Props) {
  if (loading || running) {
    return (
      <div className="flex flex-col items-center justify-center h-80 gap-4">
        <div className="w-12 h-12 rounded-2xl bg-violet-500/15 flex items-center justify-center">
          <Brain size={24} className="text-violet-400 animate-pulse" />
        </div>
        <p className="text-white/40 text-sm">Inférence GNN en cours…</p>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <div className="w-16 h-16 rounded-2xl bg-violet-500/8 border border-violet-500/15 flex items-center justify-center">
          <Brain size={32} className="text-violet-400/50" />
        </div>
        <div className="text-center">
          <p className="text-white/40 text-sm mb-1">Aucune prédiction disponible</p>
          <p className="text-white/20 text-xs mb-4">Lancez l'inférence pour analyser les propagations</p>
        </div>
        <button
          onClick={onRunGNN}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
          style={{
            background: 'rgba(124,58,237,0.15)',
            color: '#a78bfa',
            border: '1px solid rgba(124,58,237,0.30)',
          }}
        >
          <Zap size={14} />
          Lancer l'inférence GNN
        </button>
      </div>
    );
  }

  const talanImpact = result.talan_prediction?.predicted_impact ?? 0;
  const talanColor = talanImpact < -0.3 ? '#ef4444' : talanImpact > 0.3 ? '#10b981' : '#f59e0b';

  // Bar chart data — top 20 by abs(impact)
  const chartData = [...result.predictions]
    .sort((a, b) => Math.abs(b.predicted_impact) - Math.abs(a.predicted_impact))
    .slice(0, 20);

  return (
    <div className="space-y-6">
      {/* Top row: Talan gauge + systemic risk + metadata */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {/* Talan gauge */}
        <div className="col-span-2 sm:col-span-1 rounded-xl p-4 flex flex-col items-center gap-2"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
          <p className="text-[10px] text-white/30 uppercase tracking-wide">Impact Talan</p>
          <RadialGauge value={talanImpact} label="Talan" color={talanColor} />
          <div className="flex items-center gap-1.5">
            {talanImpact < 0 ? <TrendingDown size={13} className="text-red-400" />
              : talanImpact > 0 ? <TrendingUp size={13} className="text-emerald-400" />
              : <Minus size={13} className="text-white/30" />}
            <span className="text-xs text-white/50">
              Confiance: {Math.round((result.talan_prediction?.confidence ?? 0) * 100)}%
            </span>
          </div>
        </div>

        {/* Systemic risk */}
        <div className="rounded-xl p-4 flex flex-col items-center justify-center gap-2"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
          <RiskRing value={result.systemic_risk_score} />
        </div>

        {/* GNN metadata */}
        <div className="col-span-2 rounded-xl p-4 flex flex-col justify-between"
          style={{ background: 'rgba(124,58,237,0.06)', border: '1px solid rgba(124,58,237,0.15)' }}>
          <div className="flex items-center gap-2 mb-3">
            <Brain size={14} className="text-violet-400" />
            <p className="text-xs font-semibold text-violet-300">Hétérogène Temporal GNN</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'Prédictions', value: result.predictions.length },
              { label: 'Risques cachés', value: result.top_hidden_risks.length },
              { label: 'Déclencheur', value: result.trigger_event?.slice(0, 20) + (result.trigger_event?.length > 20 ? '…' : ''), mono: false },
              { label: 'Mis à jour', value: new Date(result.run_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }), mono: false },
            ].map(({ label, value, mono = true }) => (
              <div key={label}>
                <p className="text-[9px] text-white/30">{label}</p>
                <p className={`text-xs mt-0.5 text-violet-300 ${mono ? 'font-mono' : ''}`}>{value}</p>
              </div>
            ))}
          </div>
          <button onClick={onRunGNN} disabled={running}
            className="mt-3 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] font-medium transition-all"
            style={{ background: 'rgba(124,58,237,0.20)', color: '#a78bfa' }}>
            <Zap size={11} />
            Actualiser
          </button>
        </div>
      </div>

      {/* Bar chart */}
      <div className="rounded-xl p-4"
        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
        <p className="text-xs font-semibold text-white/60 mb-4">Impact prédit par entreprise</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }} barSize={14}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis
              dataKey="entity_name"
              tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 9 }}
              axisLine={false}
              tickLine={false}
              interval={0}
              angle={-35}
              textAnchor="end"
              height={50}
            />
            <YAxis
              domain={[-1, 1]}
              tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="predicted_impact" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={
                    entry.hidden_risk
                      ? '#8b5cf6'
                      : entry.predicted_impact < -0.3
                      ? '#ef4444'
                      : entry.predicted_impact > 0.3
                      ? '#10b981'
                      : '#f59e0b'
                  }
                  opacity={entry.entity_name === 'Talan' ? 1 : 0.75}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-4 mt-2 justify-center flex-wrap">
          {[
            { color: '#ef4444', label: 'Impact négatif' },
            { color: '#10b981', label: 'Impact positif' },
            { color: '#8b5cf6', label: 'Risque caché GNN' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
              <span className="text-[10px] text-white/35">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hidden risks detail */}
      {result.top_hidden_risks.length > 0 && (
        <div className="rounded-xl p-4"
          style={{ background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.20)' }}>
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={14} className="text-violet-400" />
            <p className="text-sm font-semibold text-violet-300">Top risques cachés détectés par GNN</p>
          </div>
          <div className="space-y-2">
            {result.top_hidden_risks.map((pred, i) => {
              const color = pred.predicted_impact < -0.5 ? '#ef4444'
                : pred.predicted_impact < 0 ? '#f97316' : '#10b981';
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-center gap-3 p-2.5 rounded-lg"
                  style={{ background: 'rgba(255,255,255,0.03)' }}
                >
                  <div className="w-7 h-7 rounded-lg bg-violet-500/15 flex items-center justify-center flex-shrink-0 text-[10px] text-violet-400 font-bold">
                    {pred.propagation_hops}↑
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white/75">{pred.entity_name}</p>
                    <p className="text-[10px] text-white/35 capitalize">{pred.entity_type} · {Math.round(pred.confidence * 100)}% confiance</p>
                  </div>
                  <span className="text-sm font-bold font-mono flex-shrink-0" style={{ color }}>
                    {pred.predicted_impact >= 0 ? '+' : ''}{pred.predicted_impact.toFixed(2)}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
