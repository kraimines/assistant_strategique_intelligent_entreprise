import { NavLink, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  MessageSquare,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Zap,
  Globe2,
  Radar,
  TrendingUp,
  FlaskConical,
} from 'lucide-react';
import { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';

const navItems = [
  { to: '/dashboard',        icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat',             icon: MessageSquare,   label: 'Assistant IA' },
  { to: '/world-model',      icon: Globe2,          label: 'World Model' },
  { to: '/competitive-intel',icon: Radar,           label: 'Veille Concurrentielle' },
  { to: '/market-analysis',  icon: TrendingUp,      label: 'Analyse de Marché' },
  { to: '/market-simulate',  icon: FlaskConical,    label: 'Simulation manuelle' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 68 : 236 }}
      transition={{ duration: 0.28, ease: 'easeInOut' }}
      className="flex-shrink-0 h-screen sticky top-0 flex flex-col z-40"
      style={{
        background:   'var(--bg-sidebar)',
        borderRight:  '1px solid var(--sidebar-border)',
      }}
    >
      {/* ── Logo ──────────────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-4 py-5"
        style={{ borderBottom: '1px solid var(--sidebar-border)' }}
      >
        {/* Icon mark */}
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{
            background: 'linear-gradient(135deg, #3B82F6, #2563EB)',
            boxShadow: '0 2px 8px rgba(37,99,235,0.28)',
          }}
        >
          <Zap size={17} color="#fff" />
        </div>

        {/* Wordmark — hidden when collapsed */}
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
          >
            <p
              className="font-bold text-sm leading-tight"
              style={{ color: 'var(--text-primary)' }}
            >
              Talan
            </p>
            <p className="text-xs font-medium" style={{ color: 'var(--primary)' }}>
              Intelligence
            </p>
          </motion.div>
        )}
      </div>

      {/* ── Navigation ────────────────────────────────────────────────────── */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}>
            {({ isActive }) => (
              <motion.div
                whileHover={{ x: collapsed ? 0 : 2 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 border cursor-pointer"
                style={{
                  background:   isActive ? 'var(--sidebar-active-bg)'   : 'transparent',
                  color:        isActive ? 'var(--sidebar-active-text)'  : 'var(--sidebar-text)',
                  borderColor:  isActive ? 'var(--sidebar-active-border)': 'transparent',
                  fontWeight:   isActive ? 600 : 400,
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLDivElement).style.background = 'var(--sidebar-hover-bg)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                  }
                }}
                title={collapsed ? label : undefined}
              >
                <Icon size={17} className="flex-shrink-0" />
                {!collapsed && (
                  <motion.span
                    animate={{ opacity: collapsed ? 0 : 1 }}
                    className="text-sm whitespace-nowrap truncate"
                  >
                    {label}
                  </motion.span>
                )}
              </motion.div>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <div
        className="p-3 space-y-1"
        style={{ borderTop: '1px solid var(--sidebar-border)' }}
      >
        {/* User info */}
        {!collapsed && user && (
          <div className="flex items-center gap-3 px-2 py-2 mb-1">
            {/* Avatar */}
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, #3B82F6, #14B8A6)' }}
            >
              {user.first_name?.[0]?.toUpperCase()}{user.last_name?.[0]?.toUpperCase()}
            </div>
            <div className="min-w-0">
              <p
                className="text-xs font-semibold truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {user.first_name} {user.last_name}
              </p>
              <p className="text-xs capitalize" style={{ color: 'var(--text-muted)' }}>
                {user.role}
              </p>
            </div>
          </div>
        )}

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200"
          style={{ color: 'var(--danger)' }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--danger-subtle)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
          title={collapsed ? 'Déconnexion' : undefined}
        >
          <LogOut size={16} className="flex-shrink-0" />
          {!collapsed && <span className="text-sm font-medium">Déconnexion</span>}
        </button>
      </div>

      {/* ── Collapse toggle ───────────────────────────────────────────────── */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full flex items-center justify-center transition-all duration-200 z-50"
        style={{
          background:  'var(--bg-surface)',
          border:      '1px solid var(--border-subtle)',
          color:       'var(--text-muted)',
          boxShadow:   'var(--shadow-card)',
        }}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </motion.aside>
  );
}
