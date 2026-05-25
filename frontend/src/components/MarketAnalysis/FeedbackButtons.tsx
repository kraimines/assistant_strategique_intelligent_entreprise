/**
 * FeedbackButtons — manager feedback widget for paths / recommendations / alerts.
 *
 * Displays three rating chips (👍 Pertinente, 👎 Hors-sujet, 🤔 À nuancer)
 * with an optional comment box. Persists to /market/feedback so the
 * PlausibilityScorer can be recalibrated and Trust Scores aggregated.
 */
import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ThumbsUp, ThumbsDown, HelpCircle, MessageSquare, Check, Loader2, X } from 'lucide-react';
import {
  marketAnalysisApi,
  type FeedbackItemKind,
  type FeedbackRating,
} from '../../api/marketAnalysisApi';

const RATING_CONFIG: Record<
  FeedbackRating,
  { label: string; Icon: React.ElementType; activeBg: string; activeText: string }
> = {
  relevant:  { label: 'Pertinente', Icon: ThumbsUp,   activeBg: '#DCFCE7', activeText: '#15803D' },
  off_topic: { label: 'Hors-sujet', Icon: ThumbsDown, activeBg: '#FEE2E2', activeText: '#B91C1C' },
  nuanced:   { label: 'À nuancer',  Icon: HelpCircle, activeBg: '#FEF3C7', activeText: '#B45309' },
};

interface Props {
  itemKind: FeedbackItemKind;
  itemId: string;
  itemCategory?: string;
  /** Snapshot of the rated item — persisted for later recalibration. */
  context?: Record<string, unknown>;
  /** Compact mode for inline use inside dense cards. */
  compact?: boolean;
  /** Optional callback after a successful submission. */
  onSubmitted?: (rating: FeedbackRating) => void;
}

export default function FeedbackButtons({
  itemKind, itemId, itemCategory = '', context, compact = false, onSubmitted,
}: Props) {
  const [selected,     setSelected]     = useState<FeedbackRating | null>(null);
  const [submitted,    setSubmitted]    = useState<FeedbackRating | null>(null);
  const [showComment,  setShowComment]  = useState(false);
  const [comment,      setComment]      = useState('');
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState<string | null>(null);

  async function send(rating: FeedbackRating, withComment = '') {
    if (loading || submitted) return;
    setLoading(true);
    setError(null);
    setSelected(rating);
    try {
      await marketAnalysisApi.submitFeedback({
        item_kind:     itemKind,
        item_id:       itemId,
        item_category: itemCategory,
        rating,
        comment:       withComment,
        context:       context ?? {},
      });
      setSubmitted(rating);
      setShowComment(false);
      onSubmitted?.(rating);
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? 'Erreur réseau';
      setError(msg);
      setSelected(null);
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    const cfg = RATING_CONFIG[submitted];
    return (
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md ${compact ? 'text-[10px]' : 'text-xs'}`}
        style={{ background: cfg.activeBg, color: cfg.activeText }}
      >
        <Check size={compact ? 10 : 12} />
        <span className="font-medium">Merci — feedback enregistré ({cfg.label})</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className={`flex items-center gap-1 flex-wrap ${compact ? 'text-[10px]' : 'text-xs'}`}>
        <span className="text-[var(--text-faint)] mr-1 font-medium">
          Votre avis :
        </span>
        {(['relevant', 'off_topic', 'nuanced'] as FeedbackRating[]).map((r) => {
          const cfg    = RATING_CONFIG[r];
          const Icon   = cfg.Icon;
          const active = selected === r;
          return (
            <button
              key={r}
              type="button"
              disabled={loading}
              onClick={() => send(r)}
              className={`inline-flex items-center gap-1 ${compact ? 'px-1.5 py-0.5' : 'px-2 py-1'} rounded-md border transition-all disabled:opacity-50`}
              style={{
                background:   active ? cfg.activeBg   : 'transparent',
                color:        active ? cfg.activeText : 'var(--text-secondary)',
                borderColor:  active ? cfg.activeText : 'var(--border-subtle)',
              }}
              title={cfg.label}
            >
              {loading && active
                ? <Loader2 size={compact ? 10 : 12} className="animate-spin" />
                : <Icon  size={compact ? 10 : 12} />}
              <span className="font-medium">{cfg.label}</span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setShowComment((v) => !v)}
          className={`inline-flex items-center gap-1 ${compact ? 'px-1.5 py-0.5' : 'px-2 py-1'} rounded-md border transition-all`}
          style={{
            background:   showComment ? '#E0F2FE' : 'transparent',
            color:        showComment ? '#0369A1' : 'var(--text-secondary)',
            borderColor:  showComment ? '#0369A1' : 'var(--border-subtle)',
          }}
          title="Ajouter un commentaire"
        >
          <MessageSquare size={compact ? 10 : 12} />
          {!compact && <span className="font-medium">Commenter</span>}
        </button>
      </div>

      <AnimatePresence>
        {showComment && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit   ={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="flex gap-1.5 items-start mt-1">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Précision pour l'IA (200 caractères max recommandé)…"
                rows={2}
                maxLength={2000}
                className="flex-1 text-xs px-2 py-1.5 rounded-md resize-none"
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
              <div className="flex flex-col gap-1">
                <button
                  type="button"
                  disabled={!comment.trim() || !selected || loading}
                  onClick={() => selected && send(selected, comment)}
                  className="px-2 py-1 rounded-md text-xs font-medium disabled:opacity-50"
                  style={{ background: '#0EA5E9', color: 'white' }}
                  title={!selected ? 'Choisissez d\'abord une note' : 'Envoyer le commentaire'}
                >
                  Envoyer
                </button>
                <button
                  type="button"
                  onClick={() => { setShowComment(false); setComment(''); }}
                  className="px-2 py-1 rounded-md text-xs"
                  style={{
                    background: 'transparent',
                    color: 'var(--text-faint)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <X size={12} />
                </button>
              </div>
            </div>
            {!selected && (
              <p className="text-[10px] text-[var(--text-faint)] mt-1">
                Choisissez d'abord 👍 / 👎 / 🤔 puis cliquez Envoyer.
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <p className="text-[10px] text-red-500 font-medium">⚠ {error}</p>
      )}
    </div>
  );
}
