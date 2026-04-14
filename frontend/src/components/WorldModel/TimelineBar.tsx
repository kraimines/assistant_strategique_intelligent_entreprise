/**
 * TimelineBar.tsx — Horizontal event timeline at the bottom of the explorer.
 */
import { motion } from 'framer-motion';
import type { TimelineEvent } from '../../api/graphApi';
import { EVENT_COLORS, EVENT_ICONS } from './graphConfig';

interface Props {
  events: TimelineEvent[];
  onEventClick: (event: TimelineEvent) => void;
}

export default function TimelineBar({ events, onEventClick }: Props) {
  if (events.length === 0) return null;

  return (
    <div
      className="flex-shrink-0 px-4 py-3 overflow-x-auto"
      style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
    >
      <p className="text-xs text-white/30 mb-2 font-semibold uppercase tracking-widest">
        Événements récents
      </p>
      <div className="flex items-center gap-3 pb-1">
        {events.map((ev, i) => {
          const color = EVENT_COLORS[ev.type] ?? EVENT_COLORS.default;
          const icon = EVENT_ICONS[ev.type] ?? EVENT_ICONS.default;
          return (
            <motion.button
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              onClick={() => onEventClick(ev)}
              className="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-white/5 transition-all border border-transparent hover:border-white/10 text-left group"
            >
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center text-sm flex-shrink-0"
                style={{ backgroundColor: `${color}20`, border: `1px solid ${color}40` }}
              >
                {icon}
              </div>
              <div>
                <p className="text-xs text-white/60 group-hover:text-white/90 transition-colors line-clamp-1 max-w-[160px]">
                  {ev.description}
                </p>
                <p className="text-xs text-white/20 mt-0.5">{formatDate(ev.date)}</p>
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
