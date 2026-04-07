import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Zap, Mail, Lock, User, Users, Target } from 'lucide-react';
import ParticleCanvas from '../components/ui/ParticleCanvas';
import Button from '../components/ui/Button';
import { useAuth } from '../hooks/useAuth';
import type { Role } from '../types';

const roles: { value: Role; icon: typeof User; title: string; desc: string }[] = [
  { value: 'employee', icon: User, title: 'Employé', desc: 'Accès projets, congés & performances' },
  { value: 'manager', icon: Users, title: 'Manager', desc: "Gestion d'équipe & approbations" },
  { value: 'admin', icon: Target, title: 'Direction', desc: 'Vue stratégique & simulations' },
];

export default function Signup() {
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [role, setRole] = useState<Role>('employee');
  const [showPass, setShowPass] = useState(false);
  const [passError, setPassError] = useState('');
  const { signUp, loading, error } = useAuth();

  const handleChange = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (field === 'confirmPassword' || field === 'password') {
      setPassError('');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      setPassError('Les mots de passe ne correspondent pas');
      return;
    }
    signUp({ ...form, role });
  };

  return (
    <div className="min-h-screen bg-cyber-black flex items-center justify-center relative overflow-hidden py-10">
      <ParticleCanvas />
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-cyber-violet/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/3 left-1/4 w-80 h-80 bg-cyber-cyan/5 rounded-full blur-3xl pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative z-10 w-full max-w-lg px-6"
      >
        <div
          className="rounded-2xl p-8"
          style={{
            background: 'rgba(12, 12, 20, 0.85)',
            backdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          {/* Logo */}
          <div className="flex flex-col items-center mb-7">
            <div
              className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center mb-3"
              style={{ boxShadow: '0 0 25px rgba(124,58,237,0.4)' }}
            >
              <Zap size={24} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">Créer un compte</h1>
            <p className="text-white/40 text-sm mt-1">Rejoignez Talan Intelligence Platform</p>
          </div>

          {(error || passError) && (
            <div className="mb-5 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error || passError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-white/60 text-xs font-medium">Prénom</label>
                <input
                  type="text"
                  value={form.first_name}
                  onChange={(e) => handleChange('first_name', e.target.value)}
                  required
                  placeholder="Ines"
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyber-cyan/50 transition-all"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-white/60 text-xs font-medium">Nom</label>
                <input
                  type="text"
                  value={form.last_name}
                  onChange={(e) => handleChange('last_name', e.target.value)}
                  required
                  placeholder="Ben Ali"
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyber-cyan/50 transition-all"
                />
              </div>
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <label className="text-white/60 text-xs font-medium">Email</label>
              <div className="relative">
                <Mail size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => handleChange('email', e.target.value)}
                  required
                  placeholder="vous@talan.com"
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyber-cyan/50 transition-all"
                />
              </div>
            </div>

            {/* Password */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-white/60 text-xs font-medium">Mot de passe</label>
                <div className="relative">
                  <Lock size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
                  <input
                    type={showPass ? 'text' : 'password'}
                    value={form.password}
                    onChange={(e) => handleChange('password', e.target.value)}
                    required
                    placeholder="••••••••"
                    className="w-full pl-9 pr-9 py-2.5 rounded-xl text-sm bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyber-cyan/50 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
                  >
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-white/60 text-xs font-medium">Confirmer</label>
                <input
                  type={showPass ? 'text' : 'password'}
                  value={form.confirmPassword}
                  onChange={(e) => handleChange('confirmPassword', e.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyber-cyan/50 transition-all"
                />
              </div>
            </div>

            {/* Role selector */}
            <div className="space-y-2">
              <label className="text-white/60 text-xs font-medium">Rôle</label>
              <div className="grid grid-cols-3 gap-2">
                {roles.map(({ value, icon: Icon, title, desc }) => (
                  <motion.button
                    key={value}
                    type="button"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setRole(value)}
                    className={`
                      p-3 rounded-xl border text-left transition-all duration-200
                      ${role === value
                        ? 'bg-cyber-cyan/10 border-cyber-cyan/50 shadow-[0_0_15px_rgba(0,212,255,0.15)]'
                        : 'bg-white/3 border-white/8 hover:border-white/20'
                      }
                    `}
                  >
                    <Icon
                      size={18}
                      className={`mb-1.5 ${role === value ? 'text-cyber-cyan' : 'text-white/40'}`}
                    />
                    <p className={`text-xs font-semibold ${role === value ? 'text-white' : 'text-white/60'}`}>
                      {title}
                    </p>
                    <p className="text-white/30 text-[10px] mt-0.5 leading-tight">{desc}</p>
                  </motion.button>
                ))}
              </div>
            </div>

            <Button type="submit" fullWidth loading={loading} size="lg" className="mt-2">
              Créer mon compte
            </Button>
          </form>

          <p className="text-center text-white/40 text-sm mt-5">
            Déjà un compte ?{' '}
            <Link to="/login" className="text-cyber-cyan hover:text-white transition-colors">
              Se connecter
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
