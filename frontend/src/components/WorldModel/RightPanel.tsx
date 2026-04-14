/**
 * RightPanel.tsx — Collapsible right panel showing selected node details.
 */
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, Loader2, MessageSquare, ExternalLink } from 'lucide-react';
import { graphApi } from '../../api/graphApi';
import type { GraphNode, NodeDetail } from '../../api/graphApi';
import { NODE_COLORS, NODE_ICONS } from './graphConfig';
import { useNavigate } from 'react-router-dom';

interface Props {
  node: GraphNode | null;
  onClose: () => void;
}

export default function RightPanel({ node, onClose }: Props) {
  const [detail, setDetail] = useState<NodeDetail | null>(null);
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
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="w-72 flex-shrink-0 flex flex-col overflow-y-auto"
          style={{ borderLeft: '1px solid rgba(255,255,255,0.06)' }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 p-4 border-b border-white/6">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center text-lg flex-shrink-0"
              style={{ backgroundColor: `${NODE_COLORS[node.label] ?? '#94a3b8'}22` }}
            >
              {NODE_ICONS[node.label] ?? '⬡'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-white/40">{node.label}</p>
              <p className="text-sm font-semibold text-white truncate">{node.name}</p>
            </div>
            <button onClick={onClose} className="text-white/30 hover:text-white p-1">
              <X size={16} />
            </button>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={20} className="text-cyber-cyan animate-spin" />
            </div>
          )}

          {!loading && detail && (
            <>
              {/* Properties */}
              <div className="p-4 border-b border-white/6">
                <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">
                  Propriétés
                </p>
                <div className="flex flex-col gap-2">
                  {Object.entries(detail.props)
                    .filter(([, v]) => v !== null && v !== undefined && v !== '')
                    .slice(0, 12)
                    .map(([k, v]) => (
                      <div key={k} className="flex items-start gap-2">
                        <span className="text-xs text-white/30 min-w-0 flex-shrink-0 w-28 truncate capitalize">
                          {k.replace(/_/g, ' ')}
                        </span>
                        <span className="text-xs text-white/80 break-all">{String(v)}</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Relations */}
              {detail.relations.length > 0 && (
                <div className="p-4 border-b border-white/6">
                  <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-3">
                    Relations ({detail.relations.length})
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {detail.relations.slice(0, 10).map((r, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className={`text-white/30 flex-shrink-0 ${r.direction === 'out' ? 'text-cyber-cyan/60' : 'text-cyber-violet/60'}`}>
                          {r.direction === 'out' ? '→' : '←'}
                        </span>
                        <span className="text-white/30 truncate max-w-[70px]">{r.type.replace(/_/g, ' ')}</span>
                        <ChevronRight size={10} className="text-white/20 flex-shrink-0" />
                        <span className="text-white/70 truncate">{r.name}</span>
                      </div>
                    ))}
                    {detail.relations.length > 10 && (
                      <p className="text-xs text-white/30 text-center mt-1">
                        +{detail.relations.length - 10} autres
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="p-4 flex flex-col gap-2">
                <button
                  onClick={() => navigate(`/chat?context=${encodeURIComponent(`Parle-moi de ${node.label}: ${node.name}`)}`)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-cyber-cyan border border-cyber-cyan/30 hover:bg-cyber-cyan/10 transition-all"
                >
                  <MessageSquare size={14} />
                  Voir dans le chat IA
                </button>
                <button
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-white/50 border border-white/10 hover:bg-white/5 transition-all"
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
