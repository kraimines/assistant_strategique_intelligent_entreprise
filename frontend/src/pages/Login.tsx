import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Zap, Mail, Lock } from 'lucide-react';
import ParticleCanvas from '../components/ui/ParticleCanvas';
import Button from '../components/ui/Button';
import { useAuth } from '../hooks/useAuth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const { signIn, loading, error } = useAuth();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    signIn(email, password);
  };

  return (
    <div className="min-h-screen bg-cyber-black flex items-center justify-center relative overflow-hidden">
      <ParticleCanvas />

      {/* Background glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cyber-cyan/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyber-violet/5 rounded-full blur-3xl pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-md px-6"
      >
        {/* Card */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: 'rgba(12, 12, 20, 0.85)',
            backdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.08)',
            boxShadow: '0 0 60px rgba(0,212,255,0.05)',
          }}
        >
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <motion.div
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
              className="w-14 h-14 rounded-2xl bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center mb-4"
              style={{ boxShadow: '0 0 30px rgba(0,212,255,0.3)' }}
            >
              <Zap size={28} className="text-white" />
            </motion.div>
            <h1 className="text-2xl font-bold text-white">Talan Intelligence</h1>
            <p className="text-white/40 text-sm mt-1">Connectez-vous à votre espace</p>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div className="space-y-1.5">
              <label className="text-white/60 text-sm font-medium">Email</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="vous@talan.com"
                  required
                  className="
                    w-full pl-10 pr-4 py-3 rounded-xl text-sm
                    bg-white/5 border border-white/10
                    text-white placeholder:text-white/20
                    focus:outline-none focus:border-cyber-cyan/50 focus:bg-white/8
                    transition-all duration-200
                  "
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="text-white/60 text-sm font-medium">Mot de passe</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="
                    w-full pl-10 pr-12 py-3 rounded-xl text-sm
                    bg-white/5 border border-white/10
                    text-white placeholder:text-white/20
                    focus:outline-none focus:border-cyber-cyan/50 focus:bg-white/8
                    transition-all duration-200
                  "
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <Button type="submit" fullWidth loading={loading} size="lg" className="mt-2">
              Se connecter
            </Button>
          </form>

          <p className="text-center text-white/40 text-sm mt-6">
            Pas encore de compte ?{' '}
            <Link to="/signup" className="text-cyber-cyan hover:text-white transition-colors">
              Créer un compte
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
