import { ExternalLink, Newspaper } from 'lucide-react';
import { motion } from 'framer-motion';
import type { NewsArticle } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props { articles: NewsArticle[] }

function parseDate(raw: string): string {
  if (!raw) return '';
  try {
    return new Date(raw).toLocaleDateString('fr-FR', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return raw.slice(0, 16);
  }
}

const PALETTE = ['#3B82F6', '#7C3AED', '#EA580C', '#059669', '#DB2777'];
function companyColor(company?: string): string {
  if (!company) return '#3B82F6';
  let hash = 0;
  for (const ch of company) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  return PALETTE[hash % PALETTE.length];
}

export default function NewsTimeline({ articles }: Props) {
  if (!articles.length) {
    return (
      <GlassCard animate className="p-5 flex items-center justify-center h-full min-h-[200px]">
        <p className="text-sm font-medium" style={{ color: 'var(--text-faint)' }}>
          Aucune actualité trouvée.
        </p>
      </GlassCard>
    );
  }

  return (
    <GlassCard animate className="p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Newspaper size={16} style={{ color: 'var(--primary)' }} />
        <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          Actualités récentes
          <span className="ml-2 text-sm font-normal" style={{ color: 'var(--text-faint)' }}>
            ({articles.length})
          </span>
        </h3>
      </div>

      <div className="flex flex-col gap-2.5 overflow-y-auto max-h-[420px] pr-1">
        {articles.map((article, i) => {
          const color = companyColor(article.company);
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="flex gap-3 p-3.5 rounded-2xl transition-all"
              style={{
                background: 'var(--bg-base)',
                border: '1px solid var(--border-subtle)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-strong)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-subtle)';
              }}
            >
              <div className="w-1 flex-shrink-0 rounded-full self-stretch" style={{ background: color }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold leading-snug line-clamp-2" style={{ color: 'var(--text-primary)' }}>
                    {article.title}
                  </p>
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-shrink-0 transition-colors"
                      style={{ color: 'var(--text-faint)' }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLAnchorElement).style.color = 'var(--primary)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-faint)';
                      }}
                    >
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>

                {article.summary && (
                  <p className="text-xs leading-relaxed mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                    {article.summary}
                  </p>
                )}

                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  {article.company && (
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        color,
                        background: `${color}14`,
                        border: `1px solid ${color}30`,
                      }}
                    >
                      {article.company}
                    </span>
                  )}
                  {article.source && (
                    <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                      {article.source}
                    </span>
                  )}
                  <span className="text-xs ml-auto" style={{ color: 'var(--text-faint)' }}>
                    {parseDate(article.published)}
                  </span>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </GlassCard>
  );
}
