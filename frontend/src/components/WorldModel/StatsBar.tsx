/**
 * StatsBar.tsx — Node/link count stats shown in the top header area.
 * Cold light palette.
 */
interface Props {
  nodeCount: number;
  linkCount: number;
  view:      string;
}

const VIEW_LABELS: Record<string, string> = {
  org:   'Organisation',
  crm:   'Pipeline CRM',
  hr:    'HR & Compétences',
  erp:   'ERP & Finance',
  cross: 'Relations Croisées',
};

export default function StatsBar({ nodeCount, linkCount, view }: Props) {
  return (
    <div className="flex items-center gap-4">
      {/* Current perspective pill */}
      <div
        className="px-3 py-1 rounded-full text-xs font-semibold"
        style={{
          background: 'var(--primary-subtle)',
          border:     '1px solid var(--primary-muted)',
          color:      'var(--primary-dark)',
        }}
      >
        {VIEW_LABELS[view] ?? view}
      </div>

      {/* Node count */}
      <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
        <span className="font-bold" style={{ color: 'var(--text-primary)' }}>
          {nodeCount}
        </span>{' '}
        nœuds
      </span>

      {/* Link count */}
      <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
        <span className="font-bold" style={{ color: 'var(--text-primary)' }}>
          {linkCount}
        </span>{' '}
        relations
      </span>
    </div>
  );
}
