/**
 * NewsAnalysesFeed — scrollable list of LLM-extracted causal analyses.
 * Shows event summary, type badge, severity bar, talan impact, and
 * an expandable section with causal relations.
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Newspaper, ChevronDown, ChevronUp, ArrowRight,
  TrendingDown, TrendingUp, Clock, AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import type { NewsAnalysis } from '../../api/marketAnalysisApi';

interface Props {
  analyses: NewsAnalysis[];
  loading: boolean;
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  earnings_report:      '#00d4ff',
  geopolitical_conflict:'#ef4444',
  product_launch:       '#10b981',
  macro_policy:         '#f59e0b',
  merger_acquisition:   '#7c3aed',
  regulatory:           '#f97316',
  natural_disaster:     '#ef4444',
  tech_disruption:      '#8b5cf6',
  supply_chain:         '#ec4899',
  financial_crisis:     '#dc2626',
  other:                'rgba(255,255,255,0.3)',
};

const URGENCY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#10b981',
};

function SeverityBar({ value }: { value: number }) {
  const color = value >= 0.7 ? '#ef4444' : value >= 0.4 ? '#f97316' : value >= 0.2 ? '#f59e0b' : '#10b981';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 rounded-full bg-white/8 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.5 }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
      <span className="text-[10px] font-mono" style={{ color }}>{(value * 10).toFixed(1)}/10</span>
    </div>
  );
}

function AnalysisCard({ analysis }: { analysis: NewsAnalysis }) {
  const [expanded, setExpanded] = useState(false);
  const impact = Number(analysis.talan_impact_score ?? 0);
  const typeColor = EVENT_TYPE_COLORS[analysis.event_type] ?? EVENT_TYPE_COLORS.other;
  const urgColor = URGENCY_COLORS[analysis.urgency] ?? '#10b981';
  const impactColor = impact < -0.3 ? '#ef4444'
    : impact > 0.3 ? '#10b981'
    : 'rgba(255,255,255,0.4)';

  const relations = analysis.causal_relations ?? [];
  const talanRelations = relations.filter((r) => r.talan_relevant);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="rounded-xl overflow-hidden"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: `${typeColor}15`, color: typeColor }}>
          <Newspaper size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            {/* Event type badge */}
            <span className="text-[9px] font-semibold px-2 py-0.5 rounded-md uppercase tracking-wide"
              style={{ background: `${typeColor}15`, color: typeColor }}>
              {analysis.event_type?.replace(/_/g, ' ')}
            </span>
            {/* Urgency badge */}
            <span className="text-[9px] px-1.5 py-0.5 rounded"
              style={{ background: `${urgColor}15`, color: urgColor }}>
              {analysis.urgency}
            </span>
            {/* Source badge */}
            {analysis.article_source && (
              <span className="text-[9px] px-1.5 py-0.5 rounded font-medium"
                style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.45)' }}>
                {analysis.article_source}
              </span>
            )}
            {/* Publication date */}
            <span className="text-[10px] text-white/25 flex items-center gap-1 ml-auto">
              <Clock size={9} />
              {new Date(analysis.article_published_at ?? analysis.analysis_timestamp).toLocaleString('fr-FR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          </div>
          {/* Title — clickable link if URL available */}
          {analysis.article_url ? (
            <a
              href={analysis.article_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-1.5 mb-2"
            >
              <p className="text-sm font-medium text-white/80 leading-snug line-clamp-2 group-hover:text-cyan-300 transition-colors">
                {analysis.article_title}
              </p>
              <ExternalLink size={11} className="flex-shrink-0 mt-0.5 text-white/20 group-hover:text-cyan-400 transition-colors" />
            </a>
          ) : (
            <p className="text-sm font-medium text-white/80 leading-snug line-clamp-2 mb-2">
              {analysis.article_title}
            </p>
          )}
          <p className="text-xs text-white/45 leading-relaxed line-clamp-2">
            {analysis.event_summary}
          </p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 p-1.5 rounded-lg text-white/25 hover:text-white/60 hover:bg-white/5 transition-all"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 gap-3 px-4 pb-3">
        <div>
          <p className="text-[9px] text-white/30 mb-1">Sévérité</p>
          <SeverityBar value={analysis.severity ?? 0} />
        </div>
        <div>
          <p className="text-[9px] text-white/30 mb-1 flex items-center gap-1">
            Impact Talan
            {analysis.talan_impact_score < 0
              ? <TrendingDown size={9} style={{ color: impactColor }} />
              : <TrendingUp size={9} style={{ color: impactColor }} />}
          </p>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-white/8 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${Math.abs(impact) * 100}%` }}
                transition={{ duration: 0.5 }}
                className="h-full rounded-full"
                style={{ background: impactColor }}
              />
            </div>
            <span className="text-[10px] font-mono font-semibold" style={{ color: impactColor }}>
              {impact >= 0 ? '+' : ''}{impact.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Talan action chip */}
      {analysis.talan_action_recommended && (
        <div className="mx-4 mb-3 px-3 py-2 rounded-lg flex items-start gap-2"
          style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)' }}>
          <AlertTriangle size={11} className="text-cyan-400 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-cyan-300/70 leading-relaxed">{analysis.talan_action_recommended}</p>
        </div>
      )}

      {/* Expanded: causal relations */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t"
            style={{ borderColor: 'rgba(255,255,255,0.07)' }}
          >
            <div className="p-4 space-y-3">
              {/* Talan impact reason */}
              {analysis.talan_impact_reason && (
                <div>
                  <p className="text-[10px] text-white/30 mb-1.5">Impact Talan — raison</p>
                  <p className="text-xs text-white/55 leading-relaxed">{analysis.talan_impact_reason}</p>
                </div>
              )}

              {/* Causal relations */}
              {talanRelations.length > 0 && (
                <div>
                  <p className="text-[10px] text-white/30 mb-2">Relations causales (Talan)</p>
                  <div className="space-y-2">
                    {talanRelations.slice(0, 5).map((rel, i) => {
                      const rc = rel.impact_score < 0 ? '#ef4444' : '#10b981';
                      return (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className="text-white/60 font-medium truncate max-w-[110px]" title={rel.from_entity}>
                            {rel.from_entity}
                          </span>
                          <ArrowRight size={11} className="flex-shrink-0 text-white/25" />
                          <span className="text-white/60 font-medium truncate max-w-[110px]" title={rel.to_entity}>
                            {rel.to_entity}
                          </span>
                          <span className="ml-auto font-mono text-[10px] flex-shrink-0" style={{ color: rc }}>
                            {rel.impact_score >= 0 ? '+' : ''}{rel.impact_score.toFixed(2)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Affected tickers */}
              {analysis.affected_tickers?.length > 0 && (
                <div>
                  <p className="text-[10px] text-white/30 mb-1.5">Tickers impactés</p>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.affected_tickers.map((t) => (
                      <span key={t} className="text-[10px] px-2 py-0.5 rounded font-mono"
                        style={{ background: 'rgba(0,212,255,0.08)', color: '#00d4ff' }}>
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function NewsAnalysesFeed({ analyses, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-28 rounded-xl bg-white/3 border border-white/6 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!analyses.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Newspaper size={36} className="text-white/15" />
        <p className="text-white/30 text-sm">Aucune analyse disponible</p>
        <p className="text-white/20 text-xs">Lancez un cycle pour analyser les actualités</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {analyses.map((a) => (
        <AnalysisCard key={a.id} analysis={a} />
      ))}
    </div>
  );
}
