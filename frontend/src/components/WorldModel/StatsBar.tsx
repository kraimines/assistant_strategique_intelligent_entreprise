/**
 * StatsBar.tsx — Node/link count stats shown in the top header area.
 */
interface Props {
  nodeCount: number;
  linkCount: number;
  view: string;
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
      <div className="px-3 py-1 rounded-full text-xs"
        style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: '#00d4ff' }}>
        {VIEW_LABELS[view] ?? view}
      </div>
      <span className="text-xs text-white/30">
        <span className="text-white/60 font-semibold">{nodeCount}</span> nœuds
      </span>
      <span className="text-xs text-white/30">
        <span className="text-white/60 font-semibold">{linkCount}</span> relations
      </span>
    </div>
  );
}
