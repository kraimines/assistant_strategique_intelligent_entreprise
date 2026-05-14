/**
 * TimelineBar.tsx — Horizontal event timeline at the bottom of the explorer.
 * Cold light palette — dark readable text on white/slate backgrounds.
 */
import { motion } from 'framer-motion';
import type { TimelineEvent } from '../../api/graphApi';
import { EVENT_COLORS, EVENT_ICONS } from './graphConfig';

interface Props {
  events:       TimelineEvent[];
  onEventClick: (event: TimelineEvent) => void;
}

export default function TimelineBar({ events, onEventClick }: Props) {
  if (events.length === 0) return null;

  return (
    <div
      className="flex-shrink-0 px-4 py-3 overflow-x-auto"
      style={{ background: 'var(--bg-base)' }}
    >
      <div className="flex items-center gap-3 pb-1">
        {events.map((ev, i) => {
          const color = EVENT_COLORS[ev.type] ?? EVENT_COLORS.default;
          const icon  = EVENT_ICONS[ev.type]  ?? EVENT_ICONS.default;
          return (
            <motion.button
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              onClick={() => onEventClick(ev)}
              className="flex-shrink-0 flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl transition-all duration-200 text-left group"
              style={{
                background: 'var(--bg-surface)',
                border:     '1px solid var(--border-subtle)',
                boxShadow:  'var(--shadow-card)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = `${color}50`;
                (e.currentTarget as HTMLButtonElement).style.boxShadow = 'var(--shadow-card-md)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-subtle)';
                (e.currentTarget as HTMLButtonElement).style.boxShadow = 'var(--shadow-card)';
              }}
            >
              {/* Event type icon */}
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
                style={{
                  background: `${color}18`,
                  border:     `1px solid ${color}35`,
                }}
              >
                {icon}
              </div>

              {/* Event text */}
              <div>
                <p
                  className="text-sm font-medium line-clamp-1 max-w-[160px] leading-tight"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {ev.description}
                </p>
                <p
                  className="text-xs mt-0.5 font-medium"
                  style={{ color: 'var(--text-faint)' }}
                >
                  {formatDate(ev.date)}
                </p>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('fr-FR', {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}
