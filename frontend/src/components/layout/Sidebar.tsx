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
} from 'lucide-react';
import { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Assistant IA' },
  { to: '/digital-twin', icon: Network, label: 'Digital Twin' },
  { to: '/simulation', icon: FlaskConical, label: 'Simulation' },
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
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="flex-shrink-0 h-screen sticky top-0 flex flex-col z-40"
      style={{
        background: 'rgba(10, 10, 15, 0.95)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-white/6">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center flex-shrink-0">
          <Zap size={18} className="text-white" />
        </div>
        {!collapsed && (
          <motion.div
            initial={false}
            animate={{ opacity: collapsed ? 0 : 1 }}
            transition={{ duration: 0.2 }}
          >
            <p className="text-white font-bold text-sm leading-tight">Talan</p>
            <p className="text-cyber-cyan text-xs leading-tight">Intelligence</p>
          </motion.div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}>
            {({ isActive }) => (
              <motion.div
                whileHover={{ x: 2 }}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200
                  ${isActive
                    ? 'bg-cyber-cyan/10 text-cyber-cyan border border-cyber-cyan/20'
                    : 'text-white/50 hover:text-white hover:bg-white/5'
                  }
                `}
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

      {/* User + Logout */}
      <div className="border-t border-white/6 p-3 space-y-2">
        {!collapsed && user && (
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyber-violet to-cyber-cyan flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
              {user.first_name?.[0]?.toUpperCase()}{user.last_name?.[0]?.toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-white text-xs font-medium truncate">{user.first_name} {user.last_name}</p>
              <p className="text-white/40 text-xs capitalize">{user.role}</p>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-white/40 hover:text-red-400 hover:bg-red-500/8 transition-all duration-200"
        >
          <LogOut size={16} className="flex-shrink-0" />
          {!collapsed && <span className="text-sm">Déconnexion</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-cyber-dark border border-white/10 flex items-center justify-center text-white/50 hover:text-cyber-cyan hover:border-cyber-cyan/40 transition-all duration-200 z-50"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </motion.aside>
  );
}
