import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Zap, Mail, Lock, ArrowRight } from 'lucide-react';
import Button from '../components/ui/Button';
import { useAuth } from '../hooks/useAuth';

export default function Login() {
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const { signIn, loading, error } = useAuth();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    signIn(email, password);
  };

  return (
    <div
      className="min-h-screen flex"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* ── Left decorative panel ─────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-1/2 flex-col items-center justify-center p-16 relative overflow-hidden"
        style={{
          background: 'linear-gradient(145deg, #1E3A8A 0%, #2563EB 45%, #3B82F6 75%, #06B6D4 100%)',
        }}
      >
        {/* Soft background orbs */}
        <div
          className="absolute top-16 right-16 w-64 h-64 rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, #FFFFFF, transparent)' }}
        />
        <div
          className="absolute bottom-24 left-12 w-48 h-48 rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, #BAE6FD, transparent)' }}
        />

        {/* Content */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="relative z-10 text-white text-center max-w-sm"
        >
          {/* Logo mark */}
          <div className="w-16 h-16 rounded-2xl bg-white/20 backdrop-blur-sm flex items-center justify-center mx-auto mb-8">
            <Zap size={32} color="#fff" />
          </div>

          <h2 className="text-3xl font-bold mb-4">Talan Intelligence</h2>
          <p className="text-blue-100 text-base leading-relaxed">
            Votre assistant stratégique intelligent pour les domaines RH, CRM et ERP.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2 justify-center mt-8">
            {['Intelligence artificielle', 'Données temps réel', 'Agents spécialisés'].map((f) => (
              <span
                key={f}
                className="px-3 py-1.5 rounded-full text-xs font-medium"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#E0F2FE' }}
              >
                {f}
              </span>
            ))}
          </div>
        </motion.div>
      </div>

      {/* ── Right: login form ─────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="w-full max-w-md"
        >
          {/* Header */}
          <div className="mb-8">
            {/* Mobile logo */}
            <div className="flex items-center gap-3 mb-8 lg:hidden">
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg, #3B82F6, #2563EB)' }}
              >
                <Zap size={18} color="#fff" />
              </div>
              <span className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>
                Talan Intelligence
              </span>
            </div>

            <h1
              className="text-2xl font-bold mb-1.5"
              style={{ color: 'var(--text-primary)' }}
            >
              Bon retour
            </h1>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              Connectez-vous à votre espace de travail
            </p>
          </div>

          {/* Error */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-3.5 rounded-xl text-sm flex items-start gap-3"
              style={{
                background:  'var(--danger-subtle)',
                border:      '1px solid rgba(239,68,68,0.25)',
                color:       'var(--danger)',
              }}
            >
              <span className="flex-shrink-0 mt-0.5">⚠</span>
              {error}
            </motion.div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email field */}
            <div className="space-y-1.5">
              <label
                className="text-sm font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                Adresse e-mail
              </label>
              <div className="relative">
                <Mail
                  size={15}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-faint)' }}
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="vous@talan.com"
                  required
                  className="theme-input w-full pl-10 pr-4 py-3 text-sm"
                />
              </div>
            </div>

            {/* Password field */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  className="text-sm font-medium"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Mot de passe
                </label>
                <button
                  type="button"
                  className="text-xs font-medium transition-colors"
                  style={{ color: 'var(--primary)' }}
                >
                  Mot de passe oublié ?
                </button>
              </div>
              <div className="relative">
                <Lock
                  size={15}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-faint)' }}
                />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="theme-input w-full pl-10 pr-12 py-3 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: 'var(--text-faint)' }}
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <Button
              type="submit"
              fullWidth
              loading={loading}
              size="lg"
              icon={<ArrowRight size={16} />}
              className="mt-2"
            >
              Se connecter
            </Button>
          </form>

          {/* Footer link */}
          <p
            className="text-center text-sm mt-6"
            style={{ color: 'var(--text-muted)' }}
          >
            Pas encore de compte ?{' '}
            <Link
              to="/signup"
              className="font-semibold transition-colors"
              style={{ color: 'var(--primary)' }}
            >
              Créer un compte
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
