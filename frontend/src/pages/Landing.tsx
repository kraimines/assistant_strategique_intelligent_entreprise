import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Zap, Brain, BarChart3, Network, Shield, ArrowRight } from 'lucide-react';
import ParticleCanvas from '../components/ui/ParticleCanvas';

const features = [
  { icon: Brain, title: 'Assistant IA Multi-Domaine', desc: 'Agents spécialisés RH, CRM, ERP avec LangGraph et Groq LLaMA-3', color: '#00d4ff' },
  { icon: BarChart3, title: 'Dashboards Intelligents', desc: 'KPIs temps réel, alertes prédictives et visualisations Recharts', color: '#7c3aed' },
  { icon: Network, title: 'Digital Twin', desc: 'Graphe de connaissance interactif de votre entreprise avec 50+ nœuds', color: '#10b981' },
  { icon: Shield, title: 'Rôles & Permissions', desc: 'Accès granulaires Employé / Manager / Direction avec JWT sécurisé', color: '#f59e0b' },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-cyber-black relative overflow-hidden">
      <ParticleCanvas />

      {/* Glow orbs */}
      <div className="fixed top-0 left-1/3 w-[600px] h-[400px] bg-cyber-cyan/4 rounded-full blur-[100px] pointer-events-none" />
      <div className="fixed bottom-0 right-1/3 w-[500px] h-[400px] bg-cyber-violet/4 rounded-full blur-[100px] pointer-events-none" />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-5 border-b border-white/6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center"
            style={{ boxShadow: '0 0 20px rgba(0,212,255,0.3)' }}>
            <Zap size={18} className="text-white" />
          </div>
          <span className="text-white font-bold text-lg">Talan Intelligence</span>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="px-4 py-2 text-white/60 hover:text-white text-sm transition-colors">
            Se connecter
          </Link>
          <Link
            to="/signup"
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyber-cyan to-cyber-violet text-white text-sm font-medium hover:opacity-90 transition-all"
            style={{ boxShadow: '0 0 20px rgba(0,212,255,0.25)' }}
          >
            Commencer
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <div className="relative z-10 text-center px-6 pt-24 pb-16">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
        >
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-cyber-cyan/25 bg-cyber-cyan/8 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-cyber-cyan animate-pulse" />
            <span className="text-cyber-cyan text-xs font-medium">Talan Tunisie — PFE 2026</span>
          </div>

          <h1 className="text-6xl font-black text-white mb-5 leading-tight">
            Votre Entreprise<br />
            <span className="bg-gradient-to-r from-cyber-cyan to-cyber-violet bg-clip-text text-transparent">
              Augmentée par l'IA
            </span>
          </h1>

          <p className="text-white/50 text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            Plateforme IA multi-agents pour automatiser vos décisions RH, CRM et ERP.
            Réponses en français, données réelles, streaming temps réel.
          </p>

          <div className="flex items-center justify-center gap-4">
            <Link
              to="/signup"
              className="flex items-center gap-2.5 px-8 py-4 rounded-2xl text-white font-semibold text-lg bg-gradient-to-r from-cyber-cyan to-cyber-violet hover:opacity-90 transition-all"
              style={{ boxShadow: '0 0 40px rgba(0,212,255,0.3)' }}
            >
              Démarrer gratuitement
              <ArrowRight size={18} />
            </Link>
            <Link
              to="/login"
              className="flex items-center gap-2 px-8 py-4 rounded-2xl glass border border-white/12 text-white/70 hover:text-white font-semibold text-lg transition-all hover:border-white/25"
            >
              Connexion
            </Link>
          </div>
        </motion.div>
      </div>

      {/* Feature cards */}
      <div className="relative z-10 max-w-5xl mx-auto px-6 pb-24">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
          {features.map(({ icon: Icon, title, desc, color }, i) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + i * 0.1, duration: 0.5 }}
              className="p-5 rounded-2xl glass border border-white/8 hover:border-white/15 transition-all group"
              style={{ '--glow-color': color } as React.CSSProperties}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{ background: `${color}18` }}
              >
                <Icon size={20} style={{ color }} />
              </div>
              <h3 className="text-white font-semibold text-sm mb-2">{title}</h3>
              <p className="text-white/45 text-xs leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
