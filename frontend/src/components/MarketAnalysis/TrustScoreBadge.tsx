/**
 * TrustScoreBadge — aggregated manager Trust Score for a given (kind, category).
 *
 * Pulls the latest /market/feedback/trust-scores aggregation and renders a
 * compact pill: "Trust 78% (24 avis)". When category is given, the badge
 * narrows to that bucket; otherwise it shows the global score across all
 * item kinds. Falls back silently when no data is available yet.
 */
import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, ShieldAlert, ShieldOff, Shield } from 'lucide-react';
import {
  marketAnalysisApi,
  type FeedbackItemKind,
} from '../../api/marketAnalysisApi';

interface Props {
  itemKind?: FeedbackItemKind;
  itemCategory?: string;
  /** Show "Trust manager" prefix vs. just the percentage. */
  verbose?: boolean;
  /** Hide when there are not enough samples. */
  hideIfInsufficient?: boolean;
}

const LABEL_CONFIG = {
  high:         { bg: '#DCFCE7', text: '#15803D', Icon: ShieldCheck, label: 'élevée' },
  medium:       { bg: '#FEF3C7', text: '#B45309', Icon: Shield,      label: 'moyenne' },
  low:          { bg: '#FEE2E2', text: '#B91C1C', Icon: ShieldAlert, label: 'faible' },
  insufficient: { bg: '#F1F5F9', text: '#64748B', Icon: ShieldOff,   label: 'à construire' },
} as const;

export default function TrustScoreBadge({
  itemKind, itemCategory = '', verbose = false, hideIfInsufficient = false,
}: Props) {
  const { data } = useQuery({
    queryKey: ['market-trust-scores', 90],
    queryFn:  () => marketAnalysisApi.getTrustScores(90).then((r) => r.data),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (!data) return null;

  // Pick the right bucket
  let bucket = data.overall;
  if (itemKind) {
    const found = data.buckets.find(
      (b) => b.item_kind === itemKind && (itemCategory ? b.item_category === itemCategory : true),
    );
    if (found) bucket = found;
  }
  if (!bucket) return null;
  if (hideIfInsufficient && bucket.label === 'insufficient') return null;

  const cfg = LABEL_CONFIG[bucket.label] ?? LABEL_CONFIG.insufficient;
  const Icon = cfg.Icon;

  return (
    <div
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium"
      style={{ background: cfg.bg, color: cfg.text }}
      title={
        `Trust manager (90j) : ${(bucket.trust_score * 100).toFixed(0)}%\n` +
        `${bucket.relevant} pertinents · ${bucket.nuanced} à nuancer · ${bucket.off_topic} hors-sujet`
      }
    >
      <Icon size={11} />
      <span>
        {verbose && 'Trust '}
        {bucket.total === 0
          ? '—'
          : `${(bucket.trust_score * 100).toFixed(0)}% ${cfg.label}`}
      </span>
      {bucket.total > 0 && (
        <span className="opacity-60">· {bucket.total} avis</span>
      )}
    </div>
  );
}
