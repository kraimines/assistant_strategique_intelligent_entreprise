import { ExternalLink, Newspaper } from 'lucide-react';
import { motion } from 'framer-motion';
import type { NewsArticle } from '../../api/competitiveIntelApi';
import GlassCard from '../ui/GlassCard';

interface Props {
  articles: NewsArticle[];
}

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

const COMPANY_COLORS: Record<string, string> = {
  default: '#00d4ff',
};

function companyColor(company?: string): string {
  if (!company) return COMPANY_COLORS.default;
  const colors = ['#00d4ff', '#7c3aed', '#f97316', '#22c55e', '#e879f9'];
  let hash = 0;
  for (const ch of company) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  return colors[hash % colors.length];
}

export default function NewsTimeline({ articles }: Props) {
  if (!articles.length) {
    return (
      <GlassCard animate className="p-5 flex items-center justify-center h-full min-h-[200px]">
        <p className="text-white/30 text-sm">Aucune actualité trouvée.</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard animate className="p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Newspaper size={15} className="text-cyber-cyan" />
        <h3 className="text-white font-semibold text-sm">
          Actualités récentes
          <span className="ml-2 text-white/40 font-normal">({articles.length})</span>
        </h3>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto max-h-[420px] pr-1">
        {articles.map((article, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="flex gap-3 p-3 rounded-xl bg-white/3 border border-white/6 hover:border-white/12 hover:bg-white/5 transition-all group"
          >
            {/* Company color dot */}
            <div
              className="w-1.5 flex-shrink-0 rounded-full mt-1 self-stretch"
              style={{ background: companyColor(article.company), opacity: 0.8 }}
            />

            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <p className="text-white/85 text-xs font-medium leading-snug line-clamp-2">
                  {article.title}
                </p>
                {article.url && (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-white/20 hover:text-cyber-cyan flex-shrink-0 transition-colors"
                  >
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>

              {article.summary && (
                <p className="text-white/40 text-[11px] mt-1 line-clamp-2 leading-relaxed">
                  {article.summary}
                </p>
              )}

              <div className="flex items-center gap-2 mt-2">
                {article.company && (
                  <span
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded-md"
                    style={{
                      color: companyColor(article.company),
                      background: `${companyColor(article.company)}18`,
                      border: `1px solid ${companyColor(article.company)}30`,
                    }}
                  >
                    {article.company}
                  </span>
                )}
                <span className="text-white/25 text-[10px]">{article.source}</span>
                <span className="text-white/20 text-[10px] ml-auto">
                  {parseDate(article.published)}
                </span>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </GlassCard>
  );
}
