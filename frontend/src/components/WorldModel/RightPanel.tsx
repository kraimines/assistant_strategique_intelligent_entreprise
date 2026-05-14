/**
 * RightPanel.tsx — Collapsible right panel showing selected node details.
 * Cold light palette — all text dark and readable on white background.
 */
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, Loader2, MessageSquare, ExternalLink } from 'lucide-react';
import { graphApi } from '../../api/graphApi';
import type { GraphNode, NodeDetail } from '../../api/graphApi';
import { NODE_COLORS, NODE_ICONS } from './graphConfig';
import { useNavigate } from 'react-router-dom';

interface Props {
  node:    GraphNode | null;
  onClose: () => void;
}

export default function RightPanel({ node, onClose }: Props) {
  const [detail,  setDetail]  = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!node) { setDetail(null); return; }
    setLoading(true);
    graphApi.getNodeDetail(node.id)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [node?.id]);

  return (
    <AnimatePresence>
      {node && (
        <motion.aside
          key="right-panel"
          initial={{ x: 300, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 300, opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="w-72 flex-shrink-0 flex flex-col overflow-y-auto"
          style={{
            background:  'var(--bg-surface)',
            borderLeft:  '1px solid var(--border-subtle)',
          }}
        >
          {/* ── Header ────────────────────────────────────────────────── */}
          <div
            className="flex items-center gap-3 p-4"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
          >
            {/* Node type icon */}
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0"
              style={{
                background: `${NODE_COLORS[node.label] ?? '#64748B'}18`,
                border:     `1px solid ${NODE_COLORS[node.label] ?? '#64748B'}30`,
              }}
            >
              {NODE_ICONS[node.label] ?? '⬡'}
            </div>

            <div className="flex-1 min-w-0">
              {/* Label */}
              <p
                className="text-xs font-bold uppercase tracking-wider"
                style={{ color: NODE_COLORS[node.label] ?? 'var(--text-faint)' }}
              >
                {node.label}
              </p>
              {/* Name */}
              <p
                className="text-sm font-semibold leading-tight truncate mt-0.5"
                style={{ color: 'var(--text-primary)' }}
              >
                {node.name}
              </p>
            </div>

            {/* Close */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: 'var(--text-faint)' }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-faint)';
              }}
            >
              <X size={15} />
            </button>
          </div>

          {/* ── Loading ───────────────────────────────────────────────── */}
          {loading && (
            <div className="flex items-center justify-center py-10">
              <Loader2 size={22} className="animate-spin" style={{ color: 'var(--primary)' }} />
            </div>
          )}

          {/* ── Detail ────────────────────────────────────────────────── */}
          {!loading && detail && (
            <>
              {/* Properties */}
              <div className="p-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <p
                  className="text-xs font-bold uppercase tracking-widest mb-3"
                  style={{ color: 'var(--text-faint)' }}
                >
                  Propriétés
                </p>
                <div className="flex flex-col gap-2.5">
                  {Object.entries(detail.props)
                    .filter(([, v]) => v !== null && v !== undefined && v !== '')
                    .slice(0, 12)
                    .map(([k, v]) => (
                      <div key={k} className="flex items-start gap-3">
                        <span
                          className="text-xs font-semibold min-w-0 flex-shrink-0 w-28 truncate capitalize"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {k.replace(/_/g, ' ')}
                        </span>
                        <span
                          className="text-sm font-medium break-all leading-snug"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {String(v)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Relations */}
              {detail.relations.length > 0 && (
                <div className="p-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <p
                    className="text-xs font-bold uppercase tracking-widest mb-3"
                    style={{ color: 'var(--text-faint)' }}
                  >
                    Relations ({detail.relations.length})
                  </p>
                  <div className="flex flex-col gap-2">
                    {detail.relations.slice(0, 10).map((r, i) => (
                      <div key={i} className="flex items-center gap-2">
                        {/* Direction arrow */}
                        <span
                          className="text-sm font-bold flex-shrink-0"
                          style={{
                            color: r.direction === 'out' ? 'var(--primary)' : '#8B5CF6',
                          }}
                        >
                          {r.direction === 'out' ? '→' : '←'}
                        </span>
                        {/* Relation type */}
                        <span
                          className="text-xs font-medium truncate max-w-[72px] flex-shrink-0"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {r.type.replace(/_/g, ' ')}
                        </span>
                        <ChevronRight size={10} className="flex-shrink-0" style={{ color: 'var(--border-strong)' }} />
                        {/* Target name */}
                        <span
                          className="text-sm font-semibold truncate"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {r.name}
                        </span>
                      </div>
                    ))}
                    {detail.relations.length > 10 && (
                      <p
                        className="text-xs font-medium text-center mt-1"
                        style={{ color: 'var(--text-faint)' }}
                      >
                        +{detail.relations.length - 10} autres relations
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="p-4 flex flex-col gap-2.5">
                <button
                  onClick={() => navigate(`/chat?context=${encodeURIComponent(`Parle-moi de ${node.label}: ${node.name}`)}`)}
                  className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200"
                  style={{
                    background: 'var(--primary-subtle)',
                    border:     '1px solid var(--primary-muted)',
                    color:      'var(--primary-dark)',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-muted)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-subtle)';
                  }}
                >
                  <MessageSquare size={14} />
                  Voir dans le chat IA
                </button>

                <button
                  className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200"
                  style={{
                    background: 'var(--bg-base)',
                    border:     '1px solid var(--border-subtle)',
                    color:      'var(--text-secondary)',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-strong)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-subtle)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                  }}
                >
                  <ExternalLink size={14} />
                  Lancer simulation
                </button>
              </div>
            </>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
