import { Bell, Search } from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';

/* Role badge config */
const roleConfig: Record<string, { label: string; bg: string; color: string }> = {
  employee: { label: 'Employé',  bg: '#EFF6FF', color: '#2563EB' },
  manager:  { label: 'Manager',  bg: '#F0FDFA', color: '#0D9488' },
  admin:    { label: 'Direction', bg: '#FAF5FF', color: '#7C3AED' },
};

interface TopBarProps {
  title?: string;
}

export default function TopBar({ title }: TopBarProps) {
  const { user } = useAuthStore();
  const role = roleConfig[user?.role ?? 'employee'] ?? roleConfig.employee;

  return (
    <header
      className="h-16 flex items-center justify-between px-6 flex-shrink-0"
      style={{
        background:   'var(--bg-topbar)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      {/* ── Left: page title ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {title && (
          <h1
            className="font-semibold text-base"
            style={{ color: 'var(--text-primary)' }}
          >
            {title}
          </h1>
        )}
      </div>

      {/* ── Right: search + notifications + user ─────────────────────────── */}
      <div className="flex items-center gap-3">

        {/* Search */}
        <div className="relative hidden md:block">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: 'var(--text-faint)' }}
          />
          <input
            type="text"
            placeholder="Rechercher..."
            className="theme-input pl-9 pr-4 py-2 text-sm w-52 transition-all duration-200"
            style={{ fontSize: '0.875rem' }}
          />
        </div>

        {/* Notifications */}
        <button
          className="relative w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
          style={{
            background:  'var(--bg-base)',
            border:      '1px solid var(--border-subtle)',
            color:       'var(--text-muted)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-accent)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--primary)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-subtle)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
          }}
          title="Notifications"
        >
          <Bell size={15} />
          {/* Notification dot */}
          <span
            className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--danger)' }}
          />
        </button>

        {/* User info */}
        {user && (
          <div className="flex items-center gap-2.5">
            {/* Role badge */}
            <span
              className="hidden sm:inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full"
              style={{ background: role.bg, color: role.color }}
            >
              {role.label}
            </span>

            {/* Avatar */}
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 cursor-default select-none"
              style={{ background: 'linear-gradient(135deg, #3B82F6, #14B8A6)' }}
              title={`${user.first_name} ${user.last_name}`}
            >
              {user.first_name?.[0]?.toUpperCase()}{user.last_name?.[0]?.toUpperCase()}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
