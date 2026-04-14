import { Bell, Search } from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import Badge from '../ui/Badge';

const roleLabels: Record<string, { label: string; variant: 'cyan' | 'violet' | 'emerald' }> = {
  employee: { label: 'Employé', variant: 'cyan' },
  manager: { label: 'Manager', variant: 'violet' },
  admin: { label: 'Direction', variant: 'emerald' },
};

interface TopBarProps {
  title?: string;
}

export default function TopBar({ title }: TopBarProps) {
  const { user } = useAuthStore();
  const roleConfig = user ? roleLabels[user.role] || roleLabels.employee : roleLabels.employee;

  return (
    <header
      className="h-16 flex items-center justify-between px-6 flex-shrink-0"
      style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(20px)', borderBottom: '1px solid var(--border-subtle)' }}
    >
      <div className="flex items-center gap-4">
        {title && (
          <h1 className="font-semibold text-lg" style={{ color: 'var(--text-primary)' }}>{title}</h1>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Rechercher..."
            className="theme-input pl-9 pr-4 py-2 rounded-xl text-sm focus:border-cyber-cyan/40 transition-all duration-200 w-56"
          />
        </div>

        {/* Notifications */}
        <button className="relative w-9 h-9 rounded-xl glass flex items-center justify-center hover:text-cyber-cyan hover:border-cyber-cyan/30 transition-all" style={{ color: 'var(--text-secondary)' }}>
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-cyber-cyan animate-pulse" />
        </button>

        {/* User avatar */}
        {user && (
          <div className="flex items-center gap-3">
            <Badge label={roleConfig.label} variant={roleConfig.variant} />
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-cyber-violet to-cyber-cyan flex items-center justify-center text-xs font-bold text-white">
              {user.first_name?.[0]?.toUpperCase()}{user.last_name?.[0]?.toUpperCase()}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
