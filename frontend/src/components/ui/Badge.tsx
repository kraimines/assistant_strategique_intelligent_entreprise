import type { AgentType } from '../../types';

interface BadgeProps {
  label: string;
  variant?: 'cyan' | 'violet' | 'emerald' | 'amber' | 'pink' | 'gray' | 'red';
  size?: 'sm' | 'md';
}

const variants = {
  cyan: 'bg-cyber-cyan/10 text-cyber-cyan border border-cyber-cyan/30',
  violet: 'bg-cyber-violet/10 text-cyber-violet border border-cyber-violet/30',
  emerald: 'bg-cyber-emerald/10 text-cyber-emerald border border-cyber-emerald/30',
  amber: 'bg-cyber-amber/10 text-cyber-amber border border-cyber-amber/30',
  pink: 'bg-cyber-pink/10 text-cyber-pink border border-cyber-pink/30',
  gray: 'bg-white/5 border border-white/10',
  red: 'bg-red-500/10 text-red-400 border border-red-500/30',
};

const sizes = {
  sm: 'text-xs px-2 py-0.5 rounded-md',
  md: 'text-sm px-3 py-1 rounded-lg',
};

export default function Badge({ label, variant = 'cyan', size = 'sm' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center font-medium ${variants[variant]} ${sizes[size]}`}>
      {label}
    </span>
  );
}

// Agent-specific badge
const agentConfig: Record<AgentType, { label: string; variant: BadgeProps['variant'] }> = {
  hr: { label: '👤 RH Agent', variant: 'cyan' },
  crm: { label: '📊 CRM Agent', variant: 'violet' },
  erp: { label: '⚙️ ERP Agent', variant: 'amber' },
  rag: { label: '📚 RAG', variant: 'emerald' },
  orchestrator: { label: '🤖 Orchestrateur', variant: 'pink' },
};

export function AgentBadge({ agent }: { agent: AgentType }) {
  const config = agentConfig[agent];
  return <Badge label={config.label} variant={config.variant} size="sm" />;
}
