/**
 * StrategicRecommendations — displays LLM-generated strategic recommendations
 * derived from GNN predictions + LSTM forecasts.
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb, Zap, Clock, TrendingUp, TrendingDown, Minus,
  RefreshCw, AlertTriangle, Users, DollarSign, Cpu, Shield,
  ChevronDown, ChevronUp,
} from 'lucide-react';
import type { RecommendationResult, ForecastResult } from '../../api/marketAnalysisApi';
import FeedbackButtons from './FeedbackButtons';

// Stable feedback id from the recommendation content
function buildRecFeedbackId(rec: RecommendationResult['recommendations'][number]): string {
  const base = `${rec.domain}|${rec.urgency}|${rec.horizon}|${rec.title}`;
  let h = 5381;
  for (let i = 0; i < base.length; i += 1) {
    h = ((h << 5) + h + base.charCodeAt(i)) | 0;
  }
  return `rec:${Math.abs(h).toString(36)}`;
}

const URGENCY_CONFIG = {
  critical: { label: 'Critique',  bg: '#FEF2F2', text: '#DC2626', border: '#FECACA', dot: '#DC2626' },
  high:     { label: 'Élevée',    bg: '#FFF7ED', text: '#EA580C', border: '#FED7AA', dot: '#EA580C' },
  medium:   { label: 'Moyenne',   bg: '#FEFCE8', text: '#CA8A04', border: '#FEF08A', dot: '#CA8A04' },
  low:      { label: 'Faible',    bg: '#F0FDF4', text: '#16A34A', border: '#BBF7D0', dot: '#16A34A' },
};

const HORIZON_LABEL: Record<string, string> = {
  '7_days':  '7 jours',
  '30_days': '30 jours',
  '90_days': '90 jours',
};

const DOMAIN_CONFIG: Record<string, { label: string; Icon: React.ElementType; color: string }> = {
  commercial:    { label: 'Commercial',    Icon: TrendingUp, color: '#0EA5E9' },
  rh:            { label: 'RH',            Icon: Users,      color: '#8B5CF6' },
  financier:     { label: 'Financier',     Icon: DollarSign, color: '#10B981' },
  technologique: { label: 'Technologique', Icon: Cpu,        color: '#6366F1' },
  risque:        { label: 'Risque',        Icon: Shield,     color: '#EF4444' },
};

interface Props {
  result: RecommendationResult | null;
  forecast: ForecastResult | null;
  loading: boolean;
  onGenerate: () => void;
  generating: boolean;
}

function ForecastStrip({ forecast }: { forecast: ForecastResult }) {
  const trend = forecast.trend;
  const TrendIcon = trend === 'improving' ? TrendingUp : trend === 'deteriorating' ? TrendingDown : Minus;
  const trendColor = trend === 'improving' ? '#10B981' : trend === 'deteriorating' ? '#EF4444' : '#F59E0B';
  const trendLabel = trend === 'improving' ? 'Amélioration' : trend === 'deteriorating' ? 'Dégradation' : 'Stable';

  return (
    <div
      className="rounded-2xl p-4 grid grid-cols-2 sm:grid-cols-4 gap-3"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
    >
      {[
        { label: 'Impact 7 jours', value: forecast.forecast_7d != null ? `${forecast.forecast_7d >= 0 ? '+' : ''}${forecast.forecast_7d.toFixed(3)}` : 'N/A' },
        { label: 'Impact 30 jours', value: forecast.forecast_30d != null ? `${forecast.forecast_30d >= 0 ? '+' : ''}${forecast.forecast_30d.toFixed(3)}` : 'N/A' },
        { label: 'Tendance', value: trendLabel, color: trendColor, Icon: TrendIcon },
        { label: 'Confiance LSTM', value: `${Math.round((forecast.confidence ?? 0) * 100)}%` },
      ].map(({ label, value, color, Icon: Icon2 }) => (
        <div key={label} className="text-center">
          <p className="text-[10px] font-medium text-[var(--text-muted)] mb-0.5">{label}</p>
          <div className="flex items-center justify-center gap-1">
            {Icon2 && <Icon2 size={12} style={{ color: color ?? 'var(--text-secondary)' }} />}
            <p className="text-sm font-bold" style={{ color: color ?? 'var(--text-secondary)' }}>{value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function RecommendationCard({ rec, index }: { rec: RecommendationResult['recommendations'][number]; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);
  const urg = URGENCY_CONFIG[rec.urgency] ?? URGENCY_CONFIG.medium;
  const dom = DOMAIN_CONFIG[rec.domain] ?? DOMAIN_CONFIG.commercial;
  const DomainIcon = dom.Icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07 }}
      className="rounded-2xl overflow-hidden"
      style={{ border: `1px solid ${urg.border}` }}
    >
      <button
        className="w-full flex items-start gap-3 p-4 text-left transition-colors hover:bg-black/5"
        style={{ background: urg.bg }}
        onClick={() => setExpanded(e => !e)}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: `${dom.color}18`, color: dom.color }}
        >
          <DomainIcon size={14} />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)] leading-tight">{rec.title}</p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span
              className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full"
              style={{ background: urg.bg, color: urg.text, border: `1px solid ${urg.border}` }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: urg.dot }} />
              {urg.label}
            </span>
            <span className="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
              <Clock size={9} />
              {HORIZON_LABEL[rec.horizon] ?? rec.horizon}
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full"
              style={{ background: `${dom.color}14`, color: dom.color }}
            >
              {dom.label}
            </span>
          </div>
        </div>

        <div className="flex-shrink-0 text-[var(--text-muted)] mt-0.5">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 pt-2 space-y-3" style={{ background: 'var(--bg-surface)' }}>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{rec.action}</p>

              <div className="rounded-xl p-2.5"
                style={{ background: 'rgba(14,165,233,0.06)',
                         border: '1px dashed rgba(14,165,233,0.30)' }}>
                <FeedbackButtons
                  itemKind     = "recommendation"
                  itemId       = {buildRecFeedbackId(rec)}
                  itemCategory = {rec.domain}
                  context      = {{
                    title:    rec.title,
                    urgency:  rec.urgency,
                    horizon:  rec.horizon,
                    domain:   rec.domain,
                  }}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function StrategicRecommendations({ result, forecast, loading, onGenerate, generating }: Props) {
  if (loading || generating) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="w-12 h-12 rounded-2xl bg-amber-50 flex items-center justify-center animate-pulse">
          <Lightbulb size={24} className="text-amber-500" />
        </div>
        <p className="text-[var(--text-secondary)] text-sm font-medium">
          {generating ? 'Génération des recommandations…' : 'Chargement…'}
        </p>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <div className="w-16 h-16 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center">
          <Lightbulb size={32} className="text-amber-400" />
        </div>
        <div className="text-center">
          <p className="text-[var(--text-secondary)] text-base font-semibold mb-1">Aucune recommandation disponible</p>
          <p className="text-[var(--text-muted)] text-sm mb-4">
            Lance l'inférence pour obtenir des recommandations stratégiques personnalisées
          </p>
        </div>
        <button
          onClick={onGenerate}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-semibold transition-all"
          style={{ background: '#FEF3C7', color: '#92400E', border: '1px solid #FDE68A' }}
        >
          <Zap size={14} />
          Générer les recommandations
        </button>
      </div>
    );
  }

  const impactColor = result.talan_impact < -0.3 ? '#DC2626' : result.talan_impact > 0.3 ? '#10B981' : '#F59E0B';

  return (
    <div className="space-y-5">
      {/* Context header */}
      <div
        className="rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center gap-4"
        style={{ background: 'var(--primary-subtle)', border: '1px solid var(--primary-muted)' }}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Lightbulb size={14} className="text-[var(--primary)] flex-shrink-0" />
            <p className="text-sm font-semibold text-[var(--primary-dark)]">Recommandations stratégiques Talan</p>
          </div>
          <p className="text-xs text-[var(--text-muted)] truncate">Déclencheur : {result.trigger_event}</p>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="text-xs font-mono font-bold" style={{ color: impactColor }}>
              Impact GNN : {result.talan_impact >= 0 ? '+' : ''}{result.talan_impact.toFixed(3)}
            </span>
            <span className="text-xs text-[var(--text-muted)]">
              Risque systémique : {Math.round(result.systemic_risk * 100)}%
            </span>
            <span className="text-[10px] text-[var(--text-faint)]">
              Modèle : {result.model_used}
            </span>
          </div>
        </div>
        <button
          onClick={onGenerate}
          disabled={generating}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold flex-shrink-0 transition-all"
          style={{ background: 'var(--primary)', color: 'white' }}
        >
          <RefreshCw size={11} className={generating ? 'animate-spin' : ''} />
          Actualiser
        </button>
      </div>

      {/* Forecast strip */}
      {forecast && <ForecastStrip forecast={forecast} />}

      {/* Urgency legend */}
      {result.recommendations.some(r => r.urgency === 'critical') && (
        <div
          className="flex items-center gap-2 p-3 rounded-xl text-xs"
          style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626' }}
        >
          <AlertTriangle size={13} />
          <span className="font-semibold">Action critique requise — risque systémique élevé détecté</span>
        </div>
      )}

      {/* Recommendation cards */}
      <div className="space-y-3">
        {result.recommendations.map((rec, i) => (
          <RecommendationCard key={i} rec={rec} index={i} />
        ))}
      </div>

      <p className="text-[10px] text-[var(--text-faint)] text-center">
        Généré le {new Date(result.generated_at).toLocaleString('fr-FR')} · {result.recommendations.length} recommandations
      </p>
    </div>
  );
}
