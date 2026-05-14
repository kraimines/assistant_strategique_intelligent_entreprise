import type { AgentType } from '../../types';

interface BadgeProps {
  label: string;
  variant?: 'blue' | 'teal' | 'emerald' | 'amber' | 'violet' | 'gray' | 'red'
           /* legacy aliases kept for backward compat: */
           | 'cyan' | 'violet' | 'pink';
  size?: 'sm' | 'md';
}

/* ── Variant → inline style mapping (uses CSS vars where possible) ───────── */
const variantStyle: Record<string, React.CSSProperties> = {
  // Cold palette variants
  blue:    { background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' },
  teal:    { background: '#F0FDFA', color: '#0D9488', border: '1px solid #99F6E4' },
  emerald: { background: '#ECFDF5', color: '#059669', border: '1px solid #A7F3D0' },
  amber:   { background: '#FFFBEB', color: '#D97706', border: '1px solid #FDE68A' },
  violet:  { background: '#F5F3FF', color: '#7C3AED', border: '1px solid #DDD6FE' },
  gray:    { background: '#F8FAFC', color: '#64748B', border: '1px solid #E2E8F0' },
  red:     { background: '#FEF2F2', color: '#DC2626', border: '1px solid #FECACA' },
  // Legacy aliases
  cyan:    { background: '#EFF6FF', color: '#2563EB', border: '1px solid #BFDBFE' },
  pink:    { background: '#FDF4FF', color: '#9333EA', border: '1px solid #F3E8FF' },
};

const sizes = {
  sm: 'text-xs px-2 py-0.5 rounded-md',
  md: 'text-sm px-2.5 py-1 rounded-lg',
};

export default function Badge({ label, variant = 'blue', size = 'sm' }: BadgeProps) {
  const style = variantStyle[variant] ?? variantStyle.blue;
  return (
    <span
      className={`inline-flex items-center font-semibold ${sizes[size]}`}
      style={style}
    >
      {label}
    </span>
  );
}

/* ── Agent-specific badge ────────────────────────────────────────────────── */
const agentConfig: Record<AgentType, { label: string; variant: BadgeProps['variant'] }> = {
  hr:           { label: '👤 RH',           variant: 'teal'    },
  crm:          { label: '📊 CRM',          variant: 'blue'    },
  erp:          { label: '⚙️ ERP',          variant: 'amber'   },
  rag:          { label: '📚 RAG',          variant: 'emerald' },
  orchestrator: { label: '🤖 Orchestrateur', variant: 'violet'  },
};

export function AgentBadge({ agent }: { agent: AgentType }) {
  const config = agentConfig[agent];
  return <Badge label={config.label} variant={config.variant} size="sm" />;
}
