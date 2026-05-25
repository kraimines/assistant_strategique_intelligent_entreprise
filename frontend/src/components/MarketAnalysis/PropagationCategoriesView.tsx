/**
 * PropagationCategoriesView — exhaustive, classified TGAT output.
 *
 * Spec requirements respected:
 *   - ALL events shown (no top-k cut, no merge)
 *   - Each event appears in exactly one of the 9 categories
 *   - Card shows: event name, source, impact score, target node(s),
 *     propagation path, time horizon
 *   - Empty categories are still listed (so reader can see what was *absent*)
 *   - Low-confidence classifications fall into "Unclassified / Ambiguous"
 */
import { useMemo, useState } from 'react';
import { ChevronRight, ChevronDown, ArrowRight, Calendar, Target } from 'lucide-react';
import type { PropagationPath } from '../../api/marketAnalysisApi';
import {
  classifyAndGroup, CATEGORY_META,
  type CategoryBucket, type ClassifiedPath, type EventCategory,
} from './propagationClassifier';

interface Props {
  paths: PropagationPath[];
  onSelectPath?: (path: PropagationPath) => void;
}

const ALL_CATEGORIES: EventCategory[] = [
  'External Shock', 'Competitor Action', 'Regulation / Policy',
  'Economic Signal', 'Sector Evolution', 'Technology Shift',
  'Market Trend', 'Financial Indicator', 'Company Internal Signal',
  'Unclassified / Ambiguous Signals',
];

function sevColor(score: number) {
  const a = Math.abs(score);
  if (a >= 0.5) return '#DC2626';
  if (a >= 0.3) return '#EA580C';
  if (a >= 0.15) return '#D97706';
  return '#059669';
}

function EventRow({ cp, onSelect }: { cp: ClassifiedPath; onSelect?: (p: PropagationPath) => void }) {
  const [open, setOpen] = useState(false);
  const { path, confidence } = cp;
  const sc = sevColor(path.chain_score);
  const targets = path.steps.map((s) => s.node_name);
  // "Target" in this spec = the final node before Talan, plus Talan itself
  const finalTarget = targets[targets.length - 1] ?? path.source_name;

  return (
    <div className="rounded-xl"
      style={{ border: `1px solid ${sc}22`, background: 'rgba(255,255,255,0.6)' }}>
      <button
        onClick={() => { setOpen((v) => !v); onSelect?.(path); }}
        className="w-full text-left p-3 flex items-start gap-2"
      >
        {open
          ? <ChevronDown size={13} className="mt-0.5 flex-shrink-0" style={{ color: sc }} />
          : <ChevronRight size={13} className="mt-0.5 flex-shrink-0" style={{ color: sc }} />}

        <div className="flex-1 min-w-0">
          {/* Row 1: event name + impact score + horizon */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-[12px] font-bold leading-tight" style={{ color: sc }}>
              {path.source_name}
            </span>
            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
              style={{ background: sc + '15', color: sc }}>
              {path.chain_score >= 0 ? '+' : ''}{path.chain_score.toFixed(2)}
            </span>
            <span className="text-[9px] text-[var(--text-faint)] flex items-center gap-1">
              <Calendar size={9} /> {path.time_horizon_label}
            </span>
            {confidence < 0.5 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded font-medium"
                style={{ background: '#FEF3C7', color: '#92400E' }}>
                conf. {Math.round(confidence * 100)}%
              </span>
            )}
          </div>

          {/* Row 2: source type + target (final node) */}
          <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)] mb-1.5 flex-wrap">
            <span><span className="font-bold">Source :</span> {path.source_type}</span>
            <span className="text-[var(--text-faint)]">·</span>
            <span className="flex items-center gap-1">
              <Target size={9} /> <span className="font-bold">Cible :</span> {finalTarget} → Talan
            </span>
          </div>

          {/* Row 3: compact path */}
          <div className="flex items-center gap-1 flex-wrap text-[10px]">
            <span className="px-1.5 py-0.5 rounded font-medium"
              style={{ background: '#F1F5F9', color: '#475569' }}>
              {path.source_name.length > 28 ? path.source_name.slice(0, 26) + '…' : path.source_name}
            </span>
            {path.steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1">
                <ArrowRight size={8} className="text-[var(--text-faint)]" />
                <span className="px-1.5 py-0.5 rounded"
                  style={{ background: '#F1F5F9', color: '#475569' }}>
                  {s.node_name.length > 26 ? s.node_name.slice(0, 24) + '…' : s.node_name}
                </span>
              </span>
            ))}
            <ArrowRight size={8} className="text-[var(--text-faint)]" />
            <span className="px-1.5 py-0.5 rounded font-bold"
              style={{ background: '#EFF6FF', color: '#1E40AF' }}>Talan</span>
          </div>
        </div>
      </button>

      {/* Expanded: per-step detail (still concise — full detail lives in List view) */}
      {open && (
        <div className="px-3 pb-3 space-y-1.5">
          {path.steps.map((s, i) => (
            <div key={i} className="flex gap-2 text-[10px] leading-relaxed">
              <span className="font-mono text-[var(--text-faint)] flex-shrink-0">#{i + 1}</span>
              <div className="flex-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-bold text-[var(--text-primary)]">{s.node_name}</span>
                  <span className="text-[9px] text-[var(--text-faint)]">({s.node_type})</span>
                  <span className="font-mono text-[9px]" style={{ color: sevColor(s.impact_score) }}>
                    {s.impact_score >= 0 ? '+' : ''}{s.impact_score.toFixed(2)}
                  </span>
                  <span className="text-[9px] text-[var(--text-faint)]">· {s.time_horizon}</span>
                </div>
                {s.reason && (
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                    {s.reason.length > 220 ? s.reason.slice(0, 218) + '…' : s.reason}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CategorySection({
  bucket, onSelectPath,
}: {
  bucket: { category: EventCategory; meta: typeof CATEGORY_META[EventCategory]; paths: ClassifiedPath[] | null };
  onSelectPath?: (p: PropagationPath) => void;
}) {
  const [open, setOpen] = useState(true);
  const empty = !bucket.paths || bucket.paths.length === 0;

  return (
    <div className="rounded-2xl overflow-hidden"
      style={{ border: `1px solid ${bucket.meta.border}`, background: bucket.meta.bg }}>
      <button
        onClick={() => !empty && setOpen((v) => !v)}
        className="w-full px-4 py-2.5 flex items-center gap-2.5 text-left"
        style={{ cursor: empty ? 'default' : 'pointer', opacity: empty ? 0.55 : 1 }}
      >
        <span className="text-base">{bucket.meta.emoji}</span>
        <span className="text-[13px] font-bold" style={{ color: bucket.meta.color }}>
          {bucket.category}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
          style={{ background: bucket.meta.color + '20', color: bucket.meta.color }}>
          {bucket.paths?.length ?? 0}
        </span>
        {!empty && (
          <span className="ml-auto text-[var(--text-faint)]">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
      </button>

      {!empty && open && (
        <div className="px-3 pb-3 space-y-2">
          {bucket.paths!.map((cp, i) => (
            <EventRow key={`${cp.path.source_name}-${i}`} cp={cp} onSelect={onSelectPath} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PropagationCategoriesView({ paths, onSelectPath }: Props) {
  const grouped = useMemo(() => classifyAndGroup(paths), [paths]);
  const groupedMap = useMemo(() => {
    const m = new Map<EventCategory, CategoryBucket>();
    for (const b of grouped) m.set(b.category, b);
    return m;
  }, [grouped]);

  // Coverage check: every path appears exactly once. Compute for the badge.
  const total      = paths.length;
  const classified = grouped.reduce((a, b) => a + b.paths.length, 0);

  return (
    <div className="space-y-2.5">
      {/* Coverage banner — invariant: classified === total */}
      <div className="flex items-center gap-2 text-[11px] px-3 py-1.5 rounded-lg"
        style={{ background: '#F8FAFC', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
        <span>📋 Couverture exhaustive :</span>
        <span className="font-bold" style={{ color: classified === total ? '#059669' : '#DC2626' }}>
          {classified} / {total} chemin(s) classés
        </span>
        <span className="ml-auto text-[var(--text-faint)]">
          {grouped.length} catégorie(s) actives sur {ALL_CATEGORIES.length - 1}
        </span>
      </div>

      {/* Every category — even empty — so user can see which signals are absent */}
      {ALL_CATEGORIES.map((cat) => {
        const b = groupedMap.get(cat);
        return (
          <CategorySection
            key={cat}
            bucket={{
              category: cat,
              meta:     CATEGORY_META[cat],
              paths:    b ? b.paths : null,
            }}
            onSelectPath={onSelectPath}
          />
        );
      })}
    </div>
  );
}
