import { NavLink, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  MessageSquare,
  Network,
  FlaskConical,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Zap,
  Globe2,
  Radar,
  TrendingUp,
  Sun,
  Moon,
} from 'lucide-react';
import { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { useTheme } from '../../contexts/ThemeContext';

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Assistant IA' },
  { to: '/digital-twin', icon: Network, label: 'Digital Twin' },
  { to: '/world-model', icon: Globe2, label: 'World Model' },
  { to: '/simulation', icon: FlaskConical, label: 'Simulation' },
  { to: '/competitive-intel', icon: Radar, label: 'Veille Concurrentielle' },
  { to: '/market-analysis',  icon: TrendingUp, label: 'Analyse de Marché' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const isLight = theme === 'light';

  // In light mode the sidebar is a violet gradient → use white text
  const textColor      = isLight ? 'rgba(255,255,255,0.90)' : 'var(--text-secondary)';
  const textMuted      = isLight ? 'rgba(255,255,255,0.55)' : 'var(--text-muted)';
  const borderColor    = isLight ? 'rgba(255,255,255,0.12)' : 'var(--border-subtle)';
  const activeItemBg   = isLight ? 'rgba(255,255,255,0.18)' : 'rgba(0,212,255,0.10)';
  const activeItemText = isLight ? '#ffffff'                 : 'var(--cyber-cyan)';
  const activeBorder   = isLight ? 'rgba(255,255,255,0.35)' : 'rgba(0,212,255,0.20)';

  const sidebarBg = isLight
    ? 'linear-gradient(180deg, #4c1d95 0%, #6d28d9 60%, #7c3aed 100%)'
    : 'var(--sidebar-bg)';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="flex-shrink-0 h-screen sticky top-0 flex flex-col z-40"
      style={{ background: sidebarBg, borderRight: `1px solid ${borderColor}` }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b" style={{ borderColor }}>
        <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0 backdrop-blur-sm">
          <Zap size={18} className="text-white" />
        </div>
        {!collapsed && (
          <motion.div
            initial={false}
            animate={{ opacity: collapsed ? 0 : 1 }}
            transition={{ duration: 0.2 }}
          >
            <p className="font-bold text-sm leading-tight text-white">Talan</p>
            <p className="text-xs leading-tight" style={{ color: isLight ? 'rgba(196,181,253,1)' : 'var(--cyber-cyan)' }}>
              Intelligence
            </p>
          </motion.div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}>
            {({ isActive }) => (
              <motion.div
                whileHover={{ x: 2 }}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 border"
                style={{
                  background: isActive ? activeItemBg : 'transparent',
                  color:      isActive ? activeItemText : textColor,
                  borderColor: isActive ? activeBorder : 'transparent',
                  backdropFilter: isActive && isLight ? 'blur(8px)' : undefined,
                }}
              >
                <Icon size={18} className="flex-shrink-0" />
                {!collapsed && (
                  <motion.span
                    animate={{ opacity: collapsed ? 0 : 1 }}
                    className="text-sm font-medium whitespace-nowrap"
                  >
                    {label}
                  </motion.span>
                )}
              </motion.div>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t p-3 space-y-1" style={{ borderColor }}>
        {/* User info */}
        {!collapsed && user && (
          <div className="flex items-center gap-3 px-2 py-2 mb-1">
            <div className="w-8 h-8 rounded-full bg-white/25 flex items-center justify-center text-xs font-bold text-white flex-shrink-0 backdrop-blur-sm">
              {user.first_name?.[0]?.toUpperCase()}{user.last_name?.[0]?.toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold truncate text-white">{user.first_name} {user.last_name}</p>
              <p className="text-xs capitalize" style={{ color: textMuted }}>{user.role}</p>
            </div>
          </div>
        )}

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={isLight ? 'Passer en mode sombre' : 'Passer en mode clair'}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 hover:bg-white/10"
          style={{ color: textColor }}
        >
          {isLight
            ? <Moon size={16} className="flex-shrink-0" style={{ color: 'rgba(196,181,253,1)' }} />
            : <Sun size={16} className="flex-shrink-0 text-amber-400" />}
          {!collapsed && (
            <span className="text-sm">{isLight ? 'Mode sombre' : 'Mode clair'}</span>
          )}
        </button>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 hover:bg-white/10"
          style={{ color: isLight ? 'rgba(252,165,165,0.9)' : 'rgba(248,113,113,0.7)' }}
        >
          <LogOut size={16} className="flex-shrink-0" />
          {!collapsed && <span className="text-sm">Déconnexion</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full border flex items-center justify-center transition-all duration-200 z-50"
        style={{
          background: isLight ? '#7c3aed' : 'var(--bg-surface)',
          borderColor: isLight ? 'rgba(196,181,253,0.5)' : 'var(--border-subtle)',
          color: isLight ? 'white' : 'var(--text-muted)',
        }}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </motion.aside>
  );
}
