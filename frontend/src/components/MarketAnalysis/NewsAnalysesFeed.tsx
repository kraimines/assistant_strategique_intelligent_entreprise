/**
 * NewsAnalysesFeed — LLM causal analyses with full entity + relation breakdown.
 *
 * Expanded section shows three panels:
 *   1. Entités détectées  — all extracted entities grouped by type
 *   2. Relations causales — every causal edge with its type label + impact score
 *   3. Impact Talan       — score, reason, recommended action
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Newspaper, ChevronDown, ChevronUp,
  ArrowRight, TrendingDown, TrendingUp,
  Clock, AlertTriangle, ExternalLink,
  Tag, Link2, ShieldAlert,
} from 'lucide-react';
import type { NewsAnalysis, NewsEntity, CausalRelation } from '../../api/marketAnalysisApi';

interface Props {
  analyses: NewsAnalysis[];
  loading: boolean;
}

// ── Colour palettes ────────────────────────────────────────────────────────────

const EVENT_TYPE_COLORS: Record<string, string> = {
  earnings_report:       '#3B82F6',
  geopolitical_conflict: '#EF4444',
  product_launch:        '#10B981',
  macro_policy:          '#F59E0B',
  merger_acquisition:    '#7C3AED',
  regulatory:            '#F97316',
  natural_disaster:      '#EF4444',
  tech_disruption:       '#8B5CF6',
  supply_chain:          '#EC4899',
  financial_crisis:      '#DC2626',
  other:                 '#6B7280',
};

const URGENCY_COLORS: Record<string, string> = {
  critical: '#DC2626',
  high:     '#EA580C',
  medium:   '#D97706',
  low:      '#059669',
};

/** Entity label → { bg hex, text hex } */
const ENTITY_LABEL_STYLE: Record<string, { bg: string; text: string }> = {
  Company:        { bg: '#DBEAFE', text: '#1D4ED8' },
  Competitor:     { bg: '#EDE9FE', text: '#6D28D9' },
  Technology:     { bg: '#F3E8FF', text: '#7C3AED' },
  Regulation:     { bg: '#FFEDD5', text: '#C2410C' },
  Country:        { bg: '#D1FAE5', text: '#065F46' },
  Event:          { bg: '#FEE2E2', text: '#B91C1C' },
  Sector:         { bg: '#CCFBF1', text: '#0F766E' },
  Person:         { bg: '#FCE7F3', text: '#9D174D' },
  MarketTrend:    { bg: '#FEF9C3', text: '#92400E' },
  MacroIndicator: { bg: '#E0E7FF', text: '#3730A3' },
  News:           { bg: '#F1F5F9', text: '#475569' },
};

const DEFAULT_ENTITY_STYLE = { bg: '#F3F4F6', text: '#374151' };

/** Relation type → accent colour */
const RELATION_COLOR: Record<string, string> = {
  CAUSES_IMPACT_ON:   '#DC2626',
  IMPACTS:            '#EA580C',
  INFLUENCES:         '#D97706',
  ACQUIRED:           '#7C3AED',
  COMPETES_WITH:      '#EF4444',
  LAUNCHED:           '#059669',
  RECRUITS_IN:        '#0284C7',
  BELONGS_TO_SECTOR:  '#0F766E',
  SUPPLY_CHAIN_LINK:  '#EC4899',
  OPERATES_IN:        '#6B7280',
  TRIGGERS_EVENT:     '#B91C1C',
  AFFECTS_INDICATOR:  '#4338CA',
};

const DEFAULT_REL_COLOR = '#6B7280';

// ── Helper sub-components ──────────────────────────────────────────────────────

function SeverityBar({ value }: { value: number }) {
  const color =
    value >= 0.7 ? '#DC2626' :
    value >= 0.4 ? '#EA580C' :
    value >= 0.2 ? '#D97706' : '#059669';
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.5 }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
      <span className="text-sm font-mono font-semibold" style={{ color }}>
        {(value * 10).toFixed(1)}/10
      </span>
    </div>
  );
}

function ImpactBar({ value }: { value: number }) {
  const color = value < -0.3 ? '#DC2626' : value > 0.3 ? '#059669' : '#D97706';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.abs(value) * 100}%` }}
          transition={{ duration: 0.5 }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
      <span className="text-sm font-mono font-semibold" style={{ color }}>
        {value >= 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  );
}

// ── Helpers de nettoyage ──────────────────────────────────────────────────────

/** Retourne true si le nom est utilisable (pas vide, pas "?", pas "Unknown") */
function isValidName(name?: string | null): name is string {
  if (!name) return false;
  const cleaned = name.trim();
  return cleaned.length > 0
    && cleaned !== '?'
    && cleaned.toLowerCase() !== 'unknown'
    && cleaned.toLowerCase() !== 'n/a'
    && cleaned.toLowerCase() !== 'undefined';
}

/** Nettoie un nom : retire les artefacts LLM courants */
function cleanName(name: string): string {
  return name.trim().replace(/^["'`]+|["'`]+$/g, '').trim();
}

// ── Entities panel ─────────────────────────────────────────────────────────────

function EntitiesPanel({ entities }: { entities: NewsEntity[] }) {
  // Filtrer les entités sans nom valide
  const valid = entities.filter(e => isValidName(e.name));
  if (!valid.length) return null;

  // Grouper par label
  const groups: Record<string, NewsEntity[]> = {};
  for (const e of valid) {
    const label = e.label || _capitalise(e.type) || 'Autre';
    (groups[label] ??= []).push(e);
  }

  return (
    <div>
      <p className="text-xs font-semibold text-[var(--text-muted)] mb-2 flex items-center gap-1.5">
        <Tag size={11} />
        Entités détectées ({valid.length})
      </p>
      <div className="space-y-2">
        {Object.entries(groups).map(([label, ents]) => {
          const style = ENTITY_LABEL_STYLE[label] ?? DEFAULT_ENTITY_STYLE;
          return (
            <div key={label} className="flex flex-wrap items-center gap-1.5">
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide flex-shrink-0 w-28 text-center"
                style={{ background: style.bg, color: style.text }}
              >
                {label}
              </span>
              {ents.map((e, i) => (
                <span
                  key={`${e.name}-${i}`}
                  className="text-xs px-2.5 py-0.5 rounded-full font-medium border"
                  style={{
                    background: `${style.bg}80`,
                    color: style.text,
                    borderColor: `${style.text}30`,
                  }}
                  title={e.ticker ? `Ticker: ${e.ticker}` : undefined}
                >
                  {cleanName(e.name)}
                  {e.ticker && isValidName(e.ticker) && (
                    <span className="ml-1 opacity-60 font-mono text-[10px]">
                      {e.ticker}
                    </span>
                  )}
                </span>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Relations panel ────────────────────────────────────────────────────────────

function RelationsPanel({
  relations,
  articleUrl,
}: {
  relations: CausalRelation[];
  articleUrl?: string | null;
}) {
  // Filter out relations with invalid entity names
  const valid = relations.filter(
    r => isValidName(r.from_entity) && isValidName(r.to_entity),
  );
  if (!valid.length) return null;

  const [showAll, setShowAll] = useState(false);
  const displayed = showAll ? valid : valid.slice(0, 6);

  return (
    <div>
      <p className="text-xs font-semibold text-[var(--text-muted)] mb-2 flex items-center gap-1.5">
        <Link2 size={11} />
        Relations causales ({valid.length})
      </p>
      <div className="space-y-2">
        {displayed.map((rel, i) => {
          const relType  = rel.relation_type ?? rel.type ?? 'CAUSES_IMPACT_ON';
          const relColor = RELATION_COLOR[relType] ?? DEFAULT_REL_COLOR;
          const score    = typeof rel.impact_score === 'number' ? rel.impact_score : 0;
          const conf     = typeof rel.confidence   === 'number' ? rel.confidence   : 0;
          const impColor = score < 0 ? '#DC2626' : score > 0 ? '#059669' : '#6B7280';
          const isTalan  = rel.talan_relevant;
          const reason   = rel.reason || rel.evidence || null;

          return (
            <div
              key={i}
              className="rounded-xl text-sm overflow-hidden"
              style={{
                background: isTalan ? 'var(--primary-subtle)' : 'var(--bg-base)',
                border: `1px solid ${isTalan ? 'var(--primary-muted)' : 'var(--border-subtle)'}`,
              }}
            >
              {/* main row */}
              <div className="flex items-center gap-1.5 px-3 py-2 flex-wrap">
                {/* from entity */}
                <span
                  className="font-semibold truncate max-w-[120px] flex-shrink-0"
                  style={{ color: 'var(--text-secondary)' }}
                  title={rel.from_entity}
                >
                  {cleanName(rel.from_entity)}
                </span>

                {/* relation type badge */}
                <span
                  className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide flex-shrink-0 flex items-center gap-1"
                  style={{ background: `${relColor}18`, color: relColor }}
                >
                  <ArrowRight size={9} />
                  {relType.replace(/_/g, ' ')}
                </span>

                {/* to entity */}
                <span
                  className="font-semibold truncate max-w-[120px] flex-shrink-0"
                  style={{ color: 'var(--text-secondary)' }}
                  title={rel.to_entity}
                >
                  {cleanName(rel.to_entity)}
                </span>

                {/* impact score */}
                <span
                  className="ml-auto font-mono text-xs font-bold flex-shrink-0"
                  style={{ color: impColor }}
                >
                  {score >= 0 ? '+' : ''}{score.toFixed(2)}
                </span>

                {/* confidence */}
                <span
                  className="text-[10px] font-mono flex-shrink-0"
                  style={{ color: 'var(--text-faint)' }}
                  title="Confiance LLM"
                >
                  {(conf * 100).toFixed(0)}%
                </span>

                {/* article link */}
                {articleUrl && (
                  <a
                    href={articleUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 p-0.5 rounded transition-colors hover:text-[var(--primary)]"
                    style={{ color: 'var(--text-faint)' }}
                    title="Ouvrir l'article source"
                    onClick={e => e.stopPropagation()}
                  >
                    <ExternalLink size={11} />
                  </a>
                )}
              </div>

              {/* per-relation reason (inline, collapsed) */}
              {reason && (
                <p
                  className="px-3 pb-2 text-[11px] leading-relaxed italic"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {reason}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {valid.length > 6 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-1.5 text-xs text-[var(--primary)] hover:underline"
        >
          {showAll ? 'Voir moins' : `Voir ${valid.length - 6} relation(s) de plus`}
        </button>
      )}
    </div>
  );
}

// ── Talan impact panel ─────────────────────────────────────────────────────────

function TalanImpactPanel({ analysis }: { analysis: NewsAnalysis }) {
  const impact = Number(analysis.talan_impact_score ?? 0);
  const impColor = impact < -0.3 ? '#DC2626' : impact > 0.3 ? '#059669' : '#D97706';
  const macros = analysis.macro_indicators_affected ?? [];

  return (
    <div
      className="rounded-2xl p-4 space-y-3"
      style={{
        background: `${impColor}08`,
        border: `1px solid ${impColor}25`,
      }}
    >
      <p className="text-xs font-bold uppercase tracking-wide flex items-center gap-1.5" style={{ color: impColor }}>
        <ShieldAlert size={12} />
        Impact Talan
        <span className="font-mono ml-auto text-sm">
          {impact >= 0 ? '+' : ''}{impact.toFixed(2)}
          {impact < -0.3
            ? <TrendingDown size={13} className="inline ml-1" />
            : <TrendingUp size={13} className="inline ml-1" />}
        </span>
      </p>

      {analysis.talan_impact_reason && (
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
          {analysis.talan_impact_reason}
        </p>
      )}

      {analysis.talan_action_recommended && (
        <div
          className="flex items-start gap-2 px-3 py-2.5 rounded-xl"
          style={{ background: 'var(--primary-subtle)', border: '1px solid var(--primary-muted)' }}
        >
          <AlertTriangle size={12} className="text-[var(--primary)] mt-0.5 flex-shrink-0" />
          <p className="text-sm text-[var(--primary-dark)] leading-relaxed">
            <span className="font-semibold">Action recommandée : </span>
            {analysis.talan_action_recommended}
          </p>
        </div>
      )}

      {macros.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-[var(--text-faint)] mb-1 uppercase tracking-wide">
            Indicateurs macro affectés
          </p>
          <div className="flex flex-wrap gap-1">
            {macros.map(m => (
              <span
                key={m}
                className="text-xs px-2.5 py-0.5 rounded-full font-mono"
                style={{ background: '#E0E7FF', color: '#3730A3' }}
              >
                {m}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main card ──────────────────────────────────────────────────────────────────

function AnalysisCard({ analysis }: { analysis: NewsAnalysis }) {
  const [expanded, setExpanded] = useState(false);

  const impact   = Number(analysis.talan_impact_score ?? 0);
  const typeColor = EVENT_TYPE_COLORS[analysis.event_type] ?? EVENT_TYPE_COLORS.other;
  const urgColor  = URGENCY_COLORS[analysis.urgency] ?? '#059669';

  const entities  = analysis.entities ?? [];
  const relations = analysis.causal_relations ?? [];
  const hasDetail = entities.length > 0 || relations.length > 0;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* ── Header ── */}
      <div className="flex items-start gap-3 p-5">
        <div
          className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
          style={{ background: `${typeColor}12`, color: typeColor }}
        >
          <Newspaper size={16} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span
              className="text-[11px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wide"
              style={{ background: `${typeColor}12`, color: typeColor }}
            >
              {analysis.event_type?.replace(/_/g, ' ')}
            </span>
            <span
              className="text-[11px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wide"
              style={{ background: `${urgColor}12`, color: urgColor }}
            >
              {analysis.urgency}
            </span>
            {analysis.detected_category && (
              <span
                className="text-[11px] px-2.5 py-1 rounded-full"
                style={{ background: 'var(--bg-base)', color: 'var(--text-muted)' }}
              >
                {analysis.detected_category.replace(/_/g, ' ')}
              </span>
            )}
            {analysis.article_source && (
              <span
                className="text-[11px] px-2.5 py-1 rounded-full font-medium"
                style={{ background: 'var(--bg-base)', color: 'var(--text-muted)' }}
              >
                {analysis.article_source}
              </span>
            )}
            <span className="text-xs text-[var(--text-faint)] flex items-center gap-1 ml-auto">
              <Clock size={10} />
              {new Date(
                analysis.article_published_at ?? analysis.analysis_timestamp
              ).toLocaleString('fr-FR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          </div>

          {/* Title */}
          {analysis.article_url ? (
            <a
              href={analysis.article_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-1.5 mb-2"
            >
              <p
                className="text-base font-semibold leading-snug line-clamp-2 group-hover:text-[var(--primary-dark)] transition-colors"
                style={{ color: '#111827' }}
              >
                {analysis.article_title}
              </p>
              <ExternalLink size={12} className="flex-shrink-0 mt-1 text-[var(--text-faint)] group-hover:text-[var(--primary)] transition-colors" />
            </a>
          ) : (
            <p className="text-base font-semibold leading-snug line-clamp-2 mb-2" style={{ color: '#111827' }}>
              {analysis.article_title}
            </p>
          )}

          <p className="text-sm text-[var(--text-secondary)] leading-relaxed line-clamp-2">
            {analysis.event_summary}
          </p>
        </div>

        {/* Expand button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 p-2 rounded-xl transition-all"
          style={{ color: 'var(--text-faint)' }}
          title={expanded ? 'Réduire' : 'Voir entités & relations'}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* ── Quick metrics row ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-5 pb-4">
        <div>
          <p className="text-xs font-semibold text-[var(--text-muted)] mb-1.5">Sévérité</p>
          <SeverityBar value={analysis.severity ?? 0} />
        </div>
        <div>
          <p className="text-xs font-semibold text-[var(--text-muted)] mb-1.5 flex items-center gap-1">
            Impact Talan
            {impact < 0
              ? <TrendingDown size={11} style={{ color: impact < -0.3 ? '#DC2626' : '#D97706' }} />
              : <TrendingUp size={11} style={{ color: impact > 0.3 ? '#059669' : '#D97706' }} />}
          </p>
          <ImpactBar value={impact} />
        </div>
      </div>

      {/* ── Entity / relation count chips (always visible) ── */}
      {hasDetail && (
        <div className="flex flex-wrap gap-2 px-5 pb-4">
          {entities.length > 0 && (
            <span
              className="text-[11px] px-2.5 py-1 rounded-full font-medium flex items-center gap-1"
              style={{ background: 'var(--bg-base)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
            >
              <Tag size={10} />
              {entities.length} entité{entities.length > 1 ? 's' : ''}
            </span>
          )}
          {relations.length > 0 && (
            <span
              className="text-[11px] px-2.5 py-1 rounded-full font-medium flex items-center gap-1"
              style={{ background: 'var(--bg-base)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
            >
              <Link2 size={10} />
              {relations.length} relation{relations.length > 1 ? 's' : ''}
              {relations.filter(r => r.talan_relevant).length > 0 && (
                <span className="ml-1 text-[var(--primary)] font-semibold">
                  ({relations.filter(r => r.talan_relevant).length} Talan)
                </span>
              )}
            </span>
          )}
          {analysis.extraction_confidence !== undefined && (
            <span
              className="text-[11px] px-2.5 py-1 rounded-full font-mono"
              style={{ background: 'var(--bg-base)', color: 'var(--text-faint)', border: '1px solid var(--border-subtle)' }}
            >
              confiance {(analysis.extraction_confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}

      {/* ── Expanded detail ── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="p-5 space-y-5">

              {/* 1. Entities */}
              {entities.length > 0 && (
                <EntitiesPanel entities={entities} />
              )}

              {/* 2. Relations */}
              {relations.length > 0 && (
                <RelationsPanel relations={relations} articleUrl={analysis.article_url} />
              )}

              {/* 3. Talan impact detail */}
              <TalanImpactPanel analysis={analysis} />

              {/* Affected tickers */}
              {(analysis.affected_tickers?.length ?? 0) > 0 && (
                <div>
                  <p className="text-xs font-semibold text-[var(--text-muted)] mb-1.5">Tickers impactés</p>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.affected_tickers.map((t) => (
                      <span
                        key={t}
                        className="text-xs px-2.5 py-1 rounded-full font-mono"
                        style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)' }}
                      >
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

// ── Utility ────────────────────────────────────────────────────────────────────

function _capitalise(s?: string) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
}

// ── Feed ───────────────────────────────────────────────────────────────────────

export default function NewsAnalysesFeed({ analyses, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-36 rounded-2xl bg-[var(--bg-base)] border border-[var(--border-subtle)] animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (!analyses.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Newspaper size={40} className="text-[var(--text-faint)]" />
        <p className="text-[var(--text-secondary)] text-base font-semibold">
          Aucune analyse disponible
        </p>
        <p className="text-[var(--text-muted)] text-sm">
          Lancez un cycle pour analyser les actualités filtrées
        </p>
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
