/**
 * EnrichedNewsFeed — displays articles classified by the new impact pipeline.
 *
 * Each card shows:
 *  - Impact score badge (1–10, colour-coded)
 *  - Categories chips (regulatory, competitor moves, tech launches, etc.)
 *  - Key entities tags
 *  - Talent / competitive relevance note
 *  - Collapsible full summary + link
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Newspaper, ExternalLink, ChevronDown, ChevronUp,
  Shield, Zap, TrendingUp, Globe, Users, Swords,
  Filter, RefreshCw,
} from 'lucide-react';
import type { EnrichedArticle, ArticleCategory } from '../../api/marketAnalysisApi';

// ── Category metadata ──────────────────────────────────────────────────────────

const CATEGORY_META: Record<
  ArticleCategory,
  { label: string; color: string; Icon: React.ElementType }
> = {
  regulatory_changes:      { label: 'Réglementation',     color: '#F97316', Icon: Shield    },
  competitor_moves:        { label: 'Mouvements concurrents', color: '#7C3AED', Icon: Swords },
  tech_launches:           { label: 'Lancement tech / IA', color: '#06B6D4', Icon: Zap      },
  financial_market_impact: { label: 'Impact financier',   color: '#10B981', Icon: TrendingUp },
  geopolitical_events:     { label: 'Géopolitique',       color: '#EF4444', Icon: Globe     },
  talent_market_signals:   { label: 'Marché du talent',   color: '#8B5CF6', Icon: Users     },
};

const SCORE_COLOR = (s: number) =>
  s >= 9 ? '#DC2626'
  : s >= 7 ? '#EA580C'
  : s >= 5 ? '#D97706'
  : '#059669';

// ── Single card ────────────────────────────────────────────────────────────────

function ArticleCard({ article }: { article: EnrichedArticle }) {
  const [expanded, setExpanded] = useState(false);
  const scoreColor = SCORE_COLOR(article.impact_score);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 p-5">
        {/* Impact score badge */}
        <div
          className="w-12 h-12 rounded-2xl flex flex-col items-center justify-center flex-shrink-0 font-bold"
          style={{ background: `${scoreColor}14`, color: scoreColor, border: `1.5px solid ${scoreColor}30` }}
        >
          <span className="text-lg leading-none">{article.impact_score}</span>
          <span className="text-[9px] leading-none mt-0.5 opacity-70">/10</span>
        </div>

        <div className="flex-1 min-w-0">
          {/* Categories */}
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            {article.categories.map((cat) => {
              const meta = CATEGORY_META[cat];
              if (!meta) return null;
              const { label, color, Icon } = meta;
              return (
                <span
                  key={cat}
                  className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide"
                  style={{ background: `${color}12`, color }}
                >
                  <Icon size={9} />
                  {label}
                </span>
              );
            })}
            <span className="text-[10px] text-[var(--text-faint)] ml-auto flex-shrink-0">
              {article.date ? new Date(article.date).toLocaleString('fr-FR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              }) : '—'}
            </span>
          </div>

          {/* Title */}
          {article.url ? (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-1.5 mb-1.5"
            >
              <p className="text-sm font-semibold leading-snug line-clamp-2 group-hover:text-[var(--primary-dark)] transition-colors"
                style={{ color: '#111827' }}>
                {article.title}
              </p>
              <ExternalLink size={11} className="flex-shrink-0 mt-0.5 text-[var(--text-faint)] group-hover:text-[var(--primary)] transition-colors" />
            </a>
          ) : (
            <p className="text-sm font-semibold leading-snug line-clamp-2 mb-1.5" style={{ color: '#111827' }}>
              {article.title}
            </p>
          )}

          {/* Source */}
          <span className="text-[11px] text-[var(--text-faint)]">{article.source}</span>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 p-1.5 rounded-xl transition-all"
          style={{ color: 'var(--text-faint)' }}
          aria-label={expanded ? 'Réduire' : 'Développer'}
        >
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
      </div>

      {/* ── Entities row ────────────────────────────────────────────────────── */}
      {article.key_entities.length > 0 && (
        <div className="px-5 pb-3 flex flex-wrap gap-1.5">
          {article.key_entities.slice(0, 8).map((e) => (
            <span
              key={e}
              className="text-[10px] px-2 py-0.5 rounded-full font-mono"
              style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)' }}
            >
              {e}
            </span>
          ))}
        </div>
      )}

      {/* ── Talent impact note ──────────────────────────────────────────────── */}
      {article.potential_impact_on_talent_or_competition && (
        <div
          className="mx-5 mb-4 px-4 py-2.5 rounded-xl text-[11px] leading-relaxed"
          style={{
            background: 'linear-gradient(135deg, #F0FDF4, #ECFDF5)',
            border: '1px solid #BBF7D0',
            color: '#15803D',
          }}
        >
          <span className="font-semibold">Impact RH/Concurrence : </span>
          {article.potential_impact_on_talent_or_competition}
        </div>
      )}

      {/* ── Expanded: full summary ───────────────────────────────────────────── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="p-5">
              <p className="text-xs font-semibold text-[var(--text-muted)] mb-2">Résumé complet</p>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{article.summary}</p>
              {article.key_entities.length > 8 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {article.key_entities.slice(8).map((e) => (
                    <span
                      key={e}
                      className="text-[10px] px-2 py-0.5 rounded-full font-mono"
                      style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)' }}
                    >
                      {e}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Category filter bar ────────────────────────────────────────────────────────

const ALL_CATEGORIES = Object.keys(CATEGORY_META) as ArticleCategory[];

function CategoryFilter({
  selected,
  onChange,
}: {
  selected: ArticleCategory | null;
  onChange: (cat: ArticleCategory | null) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-4">
      <button
        onClick={() => onChange(null)}
        className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-semibold transition-all"
        style={{
          background: selected === null ? 'var(--primary-subtle)' : 'var(--bg-surface)',
          color: selected === null ? 'var(--primary-dark)' : 'var(--text-muted)',
          border: `1px solid ${selected === null ? 'var(--primary-muted)' : 'var(--border-subtle)'}`,
        }}
      >
        <Filter size={10} />
        Tous
      </button>
      {ALL_CATEGORIES.map((cat) => {
        const { label, color } = CATEGORY_META[cat];
        const active = selected === cat;
        return (
          <button
            key={cat}
            onClick={() => onChange(active ? null : cat)}
            className="px-3 py-1.5 rounded-full text-[11px] font-semibold transition-all uppercase tracking-wide"
            style={{
              background: active ? `${color}14` : 'var(--bg-surface)',
              color: active ? color : 'var(--text-muted)',
              border: `1px solid ${active ? `${color}40` : 'var(--border-subtle)'}`,
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  articles: EnrichedArticle[];
  loading: boolean;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export default function EnrichedNewsFeed({ articles, loading, onRefresh, refreshing }: Props) {
  const [minScore, setMinScore] = useState(5);
  const [catFilter, setCatFilter] = useState<ArticleCategory | null>(null);

  const filtered = articles
    .filter((a) => a.impact_score >= minScore)
    .filter((a) => !catFilter || a.categories.includes(catFilter));

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-28 rounded-2xl bg-[var(--bg-base)] border border-[var(--border-subtle)] animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Min score slider */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--text-muted)] font-semibold">Score min :</span>
          <input
            type="range"
            min={1}
            max={10}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-24 accent-blue-500"
          />
          <span
            className="text-sm font-mono font-bold w-6 text-center"
            style={{ color: SCORE_COLOR(minScore) }}
          >
            {minScore}
          </span>
        </div>

        <span className="text-[11px] text-[var(--text-faint)] ml-auto">
          {filtered.length} article{filtered.length !== 1 ? 's' : ''}
        </span>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold transition-all"
            style={{
              background: 'var(--bg-surface)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
            Actualiser
          </button>
        )}
      </div>

      {/* Category filter */}
      <CategoryFilter selected={catFilter} onChange={setCatFilter} />

      {/* Articles */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Newspaper size={40} className="text-[var(--text-faint)]" />
          <p className="text-[var(--text-secondary)] text-base font-semibold">
            {articles.length === 0 ? 'Aucun article collecté' : 'Aucun article avec ce filtre'}
          </p>
          <p className="text-[var(--text-muted)] text-sm text-center max-w-sm">
            {articles.length === 0
              ? 'Lancez un cycle de collecte via le bouton "Lancer maintenant" pour alimenter la veille.'
              : 'Abaissez le score minimum ou changez la catégorie'}
          </p>
          {articles.length === 0 && onRefresh && (
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold mt-2 transition-all"
              style={{
                background: 'var(--primary-subtle)',
                color: 'var(--primary-dark)',
                border: '1px solid var(--primary-muted)',
              }}
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
              Actualiser depuis les sources
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((a, i) => (
            <ArticleCard key={`${a.url}-${i}`} article={a} />
          ))}
        </div>
      )}
    </div>
  );
}
