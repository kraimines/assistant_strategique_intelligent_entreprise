/**
 * PropagationTimelineView — horizontal timeline of TGAT propagation events.
 *
 * Time axis layout:
 *   - Anchor t₀ = GNN run_at  (left side, ≈ "today")
 *   - Each path is plotted at t₀ + horizon_days(path), where horizon is
 *     derived from path.steps' worst (slowest) time_horizon — that captures
 *     the moment the effect reaches Talan.
 *   - X scale = log-ish bucket so immediate (7d) and long (180d) both readable.
 *
 * Why frontend-only / why this approximation:
 *   Backend doesn't currently expose article_published_at per path. The user
 *   picked "published_at as anchor + horizon as forward projection" — until
 *   that field is plumbed through, run_at is the best proxy (it IS when the
 *   snapshot reflects the world state). Mark visually as "Aujourd'hui" so the
 *   reader understands the anchor.
 */
import { useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import type { PropagationPath } from '../../api/marketAnalysisApi';
import {
  classifyPath, CATEGORY_META, horizonToOffsetDays,
  type EventCategory,
} from './propagationClassifier';

interface Props {
  paths:     PropagationPath[];
  runAt?:    string;  // ISO timestamp from GNNResult.run_at; falls back to now
  onSelect?: (p: PropagationPath) => void;
}

// Buckets along the X axis (logarithmic-feeling spacing)
const BUCKETS = [
  { key: 'now',       label: "Aujourd'hui",      maxDays: 0,   xPct: 5   },
  { key: 'immediate', label: '1-2 sem (T+7j)',   maxDays: 14,  xPct: 22  },
  { key: 'short',     label: '2-4 sem (T+30j)',  maxDays: 35,  xPct: 42  },
  { key: 'medium',    label: '1-3 mois (T+90j)', maxDays: 100, xPct: 65  },
  { key: 'long',      label: '3-6 mois (T+180j)',maxDays: 365, xPct: 90  },
] as const;

function bucketForDays(days: number) {
  for (const b of BUCKETS) if (days <= b.maxDays) return b;
  return BUCKETS[BUCKETS.length - 1];
}

// "Worst" (latest) horizon across all steps — that's when Talan is hit
function pathHorizonDays(path: PropagationPath): number {
  if (!path.steps?.length) return horizonToOffsetDays(path.time_horizon_label);
  let max = 0;
  for (const s of path.steps) {
    max = Math.max(max, horizonToOffsetDays(s.time_horizon));
  }
  return max || horizonToOffsetDays(path.time_horizon_label);
}

function sevColor(score: number) {
  const a = Math.abs(score);
  if (a >= 0.5) return '#DC2626';
  if (a >= 0.3) return '#EA580C';
  if (a >= 0.15) return '#D97706';
  return '#059669';
}

interface PlottedEvent {
  path:       PropagationPath;
  category:   EventCategory;
  days:       number;
  xPct:       number;
  yLane:      number;  // for vertical stacking when events collide
  laneOffset: number;
}

function layoutEvents(paths: PropagationPath[], runAt?: string): { events: PlottedEvent[]; anchor: Date } {
  const anchor = runAt ? new Date(runAt) : new Date();
  const events: PlottedEvent[] = paths.map((p) => {
    const days = pathHorizonDays(p);
    const b    = bucketForDays(days);
    return {
      path:       p,
      category:   classifyPath(p).category,
      days,
      xPct:       b.xPct,
      yLane:      0,
      laneOffset: 0,
    };
  });

  // Simple lane allocation: events whose xPct are within 8% share a column, get y-stacked
  events.sort((a, b) => a.xPct - b.xPct);
  const columns: { center: number; count: number }[] = [];
  for (const e of events) {
    const col = columns.find((c) => Math.abs(c.center - e.xPct) < 8);
    if (col) {
      e.yLane      = col.count;
      e.laneOffset = col.count;
      col.count   += 1;
    } else {
      columns.push({ center: e.xPct, count: 1 });
      e.yLane = 0;
    }
  }
  return { events, anchor };
}

function EventPin({
  event, onSelect, hovered, setHovered,
}: {
  event:      PlottedEvent;
  onSelect?:  (p: PropagationPath) => void;
  hovered:    string | null;
  setHovered: (k: string | null) => void;
}) {
  const meta = CATEGORY_META[event.category];
  const sc   = sevColor(event.path.chain_score);
  const r    = 9 + Math.min(6, Math.abs(event.path.chain_score) * 8);
  const y    = 50 + event.laneOffset * 38;  // px from top of plot area
  const key  = `${event.path.source_name}-${event.days}`;
  const isHovered = hovered === key;

  return (
    <div
      onMouseEnter={() => setHovered(key)}
      onMouseLeave={() => setHovered(null)}
      onClick={() => onSelect?.(event.path)}
      style={{
        position:  'absolute',
        left:      `${event.xPct}%`,
        top:       y,
        transform: 'translate(-50%, -50%)',
        cursor:    'pointer',
        zIndex:    isHovered ? 10 : 2,
      }}
    >
      {/* Pin dot */}
      <div style={{
        width: r * 2, height: r * 2, borderRadius: '50%',
        background: meta.color,
        border: `2px solid ${sc}`,
        boxShadow: isHovered
          ? `0 0 0 4px ${meta.color}30, 0 2px 8px rgba(0,0,0,0.18)`
          : `0 2px 4px rgba(0,0,0,0.12)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: r, color: 'white',
        transition: 'box-shadow .15s',
      }}>
        {meta.emoji}
      </div>

      {/* Tooltip card on hover */}
      {isHovered && (
        <div style={{
          position: 'absolute', top: r * 2 + 6, left: '50%',
          transform: 'translateX(-50%)',
          background: 'white',
          border: `1px solid ${meta.border}`,
          borderRadius: 10,
          padding: '8px 10px',
          minWidth: 220, maxWidth: 280,
          boxShadow: '0 6px 16px rgba(0,0,0,0.12)',
          fontSize: 11,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{
              padding: '1px 5px', borderRadius: 4, fontSize: 9, fontWeight: 700,
              background: meta.color + '20', color: meta.color,
            }}>{meta.short}</span>
            <span style={{ fontWeight: 700, color: sc, fontFamily: 'monospace', fontSize: 10 }}>
              {event.path.chain_score >= 0 ? '+' : ''}{event.path.chain_score.toFixed(2)}
            </span>
            <span style={{ marginLeft: 'auto', fontSize: 9, color: '#94A3B8' }}>
              T+{event.days}j
            </span>
          </div>
          <div style={{ fontWeight: 700, fontSize: 11, lineHeight: 1.3, color: '#1E293B', marginBottom: 4 }}>
            {event.path.source_name}
          </div>
          <div style={{ fontSize: 10, color: '#64748B', lineHeight: 1.4 }}>
            {event.path.steps.length} étape(s) · {event.path.hops} saut(s) ·{' '}
            confiance {Math.round(event.path.chain_conf * 100)}%
          </div>
          <div style={{ fontSize: 9, color: '#94A3B8', marginTop: 4 }}>
            Cliquez pour ouvrir le chemin complet
          </div>
        </div>
      )}
    </div>
  );
}

export default function PropagationTimelineView({ paths, runAt, onSelect }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  const { events, anchor } = useMemo(() => layoutEvents(paths, runAt), [paths, runAt]);

  // Plot height grows with max lane stacking
  const maxLane    = events.reduce((m, e) => Math.max(m, e.laneOffset), 0);
  const plotHeight = Math.max(180, 80 + (maxLane + 1) * 42);

  // Category legend (only categories actually present)
  const presentCats = useMemo(() => {
    const s = new Set<EventCategory>();
    for (const e of events) s.add(e.category);
    return Array.from(s);
  }, [events]);

  if (paths.length === 0) {
    return (
      <div className="rounded-xl p-6 text-center text-[12px]"
        style={{ background: '#F8FAFC', border: '1px dashed var(--border-subtle)', color: 'var(--text-muted)' }}>
        Aucun chemin de propagation à placer sur la timeline.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2 text-[11px]"
        style={{ color: 'var(--text-muted)' }}>
        <Calendar size={13} />
        <span>Timeline TGAT</span>
        <span className="text-[var(--text-faint)]">·</span>
        <span>Ancre : <span className="font-semibold">{anchor.toLocaleDateString('fr-FR')}</span></span>
        <span className="text-[var(--text-faint)]">·</span>
        <span>{events.length} événement(s)</span>
      </div>

      {/* Plot area */}
      <div className="rounded-2xl overflow-visible relative"
        style={{
          background: 'linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 100%)',
          border: '1px solid var(--border-subtle)',
          padding: '24px 24px 48px 24px',
          minHeight: plotHeight + 48,
        }}>
        {/* Time axis line */}
        <div style={{
          position: 'absolute', left: 24, right: 24, top: 70,
          height: 2, background: 'linear-gradient(90deg, #3B82F6 0%, #94A3B8 50%, #CBD5E1 100%)',
          borderRadius: 1,
        }} />

        {/* Bucket ticks + labels */}
        {BUCKETS.map((b) => (
          <div key={b.key} style={{
            position: 'absolute', left: `calc(${b.xPct}% + 0px)`, top: 60,
            transform: 'translateX(-50%)',
          }}>
            <div style={{
              width: 2, height: 18, background: b.key === 'now' ? '#3B82F6' : '#94A3B8',
              margin: '0 auto',
            }} />
            <div style={{
              fontSize: 10, color: b.key === 'now' ? '#1E40AF' : '#64748B',
              fontWeight: b.key === 'now' ? 700 : 500,
              marginTop: 4, whiteSpace: 'nowrap', textAlign: 'center',
            }}>
              {b.label}
            </div>
          </div>
        ))}

        {/* Pins */}
        {events.map((e, i) => (
          <EventPin
            key={`${e.path.source_name}-${i}`}
            event={e}
            onSelect={onSelect}
            hovered={hovered}
            setHovered={setHovered}
          />
        ))}
      </div>

      {/* Legend */}
      {presentCats.length > 0 && (
        <div className="flex items-center flex-wrap gap-2 text-[10px]">
          <span className="text-[var(--text-faint)] font-semibold uppercase">Catégories :</span>
          {presentCats.map((c) => {
            const m = CATEGORY_META[c];
            return (
              <span key={c} className="px-2 py-0.5 rounded-full flex items-center gap-1"
                style={{ background: m.bg, color: m.color, border: `1px solid ${m.border}` }}>
                <span>{m.emoji}</span>
                <span className="font-semibold">{c}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
