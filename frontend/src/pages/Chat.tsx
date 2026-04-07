import { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Plus, MessageSquare, Zap, Mic, AlertTriangle } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import MessageBubble from '../components/chat/MessageBubble';
import { useChat } from '../hooks/useChat';
import { useAuthStore } from '../stores/authStore';
import { nanoid } from '../utils/nanoid';
import type { Conversation } from '../types';

const roleChips: Record<string, string[]> = {
  employee: [
    'Montre mes projets actifs',
    'Demander un congé la semaine prochaine',
    'Mon score de performance',
    'Heures travaillées ce mois',
  ],
  manager: [
    'Charge de travail équipe cette semaine',
    'Congés en attente d\'approbation',
    'Alertes retard de projets',
    'Top performer ce trimestre',
  ],
  admin: [
    'Revenus vs objectif',
    'Risques de désengagement clients',
    'Simulation: perte du top client',
    'KPIs stratégiques globaux',
  ],
};

const predictiveBanners = [
  { type: 'warning', message: '3 projets à risque de dépassement de délai — Cliquez pour investiguer' },
  { type: 'critical', message: 'Client Tunisie Telecom: signaux de désengagement détectés' },
  { type: 'info', message: 'Pic de charge inhabituel dans l\'équipe Engineering ce mois' },
];

interface ConvSummary {
  id: string;
  title: string;
  updatedAt: Date;
}

export default function Chat() {
  const { user } = useAuthStore();
  const { messages, isStreaming, sendMessage, clearMessages } = useChat();
  const [input, setInput] = useState('');
  const [conversations, setConversations] = useState<ConvSummary[]>([
    { id: 'c1', title: 'Analyse RH Q1 2026', updatedAt: new Date('2026-04-06') },
    { id: 'c2', title: 'Opportunités CRM', updatedAt: new Date('2026-04-05') },
    { id: 'c3', title: 'Facturation ERP', updatedAt: new Date('2026-04-04') },
  ]);
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [showBanner, setShowBanner] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const text = input.trim();
    setInput('');
    sendMessage(text);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    const id = nanoid();
    setConversations((prev) => [{ id, title: 'Nouvelle conversation', updatedAt: new Date() }, ...prev]);
    setActiveConv(id);
    clearMessages();
  };

  const chips = roleChips[user?.role || 'employee'];
  const banner = predictiveBanners[showBanner % predictiveBanners.length];

  return (
    <AppShell title="Assistant IA">
      <div className="flex h-full">
        {/* Left sidebar - conversations */}
        <aside
          className="w-64 flex-shrink-0 flex flex-col border-r border-white/6 h-full"
          style={{ background: 'rgba(10,10,15,0.8)' }}
        >
          <div className="p-3">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-cyber-cyan/10 border border-cyber-cyan/25 text-cyber-cyan text-sm font-medium hover:bg-cyber-cyan/18 transition-all"
            >
              <Plus size={16} />
              Nouvelle conversation
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-2 py-1 space-y-1">
            {conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => setActiveConv(c.id)}
                className={`
                  w-full text-left px-3 py-2.5 rounded-xl transition-all group
                  ${activeConv === c.id
                    ? 'bg-white/8 text-white'
                    : 'text-white/50 hover:text-white/80 hover:bg-white/5'
                  }
                `}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} className="flex-shrink-0 text-white/30" />
                  <span className="text-xs truncate">{c.title}</span>
                </div>
                <p className="text-white/25 text-[10px] mt-1 pl-5">
                  {c.updatedAt.toLocaleDateString('fr-FR')}
                </p>
              </button>
            ))}
          </div>
        </aside>

        {/* Main chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Predictive banner */}
          <AnimatePresence>
            <motion.div
              key={showBanner}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`
                flex items-center justify-between gap-3 px-5 py-2.5 text-sm border-b cursor-pointer
                ${banner.type === 'critical'
                  ? 'bg-red-500/8 border-red-500/20 text-red-300'
                  : banner.type === 'warning'
                  ? 'bg-amber-500/8 border-amber-500/20 text-amber-300'
                  : 'bg-cyber-cyan/8 border-cyber-cyan/15 text-cyber-cyan'
                }
              `}
              onClick={() => setShowBanner((s) => s + 1)}
            >
              <div className="flex items-center gap-2.5">
                <AlertTriangle size={14} className="flex-shrink-0" />
                <span>{banner.message}</span>
              </div>
              <span className="text-white/25 text-xs flex-shrink-0">Cliquez pour suivant →</span>
            </motion.div>
          </AnimatePresence>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
                <motion.div
                  animate={{ rotate: [0, 5, -5, 0] }}
                  transition={{ duration: 4, repeat: Infinity }}
                  className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center"
                  style={{ boxShadow: '0 0 40px rgba(0,212,255,0.2)' }}
                >
                  <Zap size={32} className="text-white" />
                </motion.div>
                <div>
                  <h2 className="text-white text-xl font-bold mb-2">Comment puis-je vous aider ?</h2>
                  <p className="text-white/40 text-sm">Posez une question sur vos données RH, CRM ou ERP</p>
                </div>

                {/* Quick suggestion chips */}
                <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                  {chips.map((chip) => (
                    <motion.button
                      key={chip}
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => {
                        setInput(chip);
                        inputRef.current?.focus();
                      }}
                      className="px-4 py-2 rounded-xl glass border border-white/10 text-white/60 text-sm hover:text-white hover:border-cyber-cyan/35 transition-all"
                    >
                      {chip}
                    </motion.button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="max-w-3xl mx-auto">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input area */}
          <div className="px-6 py-4 border-t border-white/6">
            <div className="max-w-3xl mx-auto">
              <div
                className="flex items-end gap-3 rounded-2xl p-3"
                style={{
                  background: 'rgba(18,18,28,0.85)',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  boxShadow: isStreaming ? '0 0 20px rgba(0,212,255,0.1)' : 'none',
                  transition: 'box-shadow 0.3s',
                }}
              >
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Posez votre question... (Entrée pour envoyer, Maj+Entrée pour saut de ligne)"
                  disabled={isStreaming}
                  rows={1}
                  className="
                    flex-1 bg-transparent text-white text-sm placeholder:text-white/25
                    focus:outline-none resize-none max-h-36 overflow-y-auto
                    leading-relaxed py-1
                  "
                  style={{ fieldSizing: 'content' } as React.CSSProperties}
                />

                {/* Mic button */}
                <button className="w-9 h-9 rounded-xl flex items-center justify-center text-white/30 hover:text-white/60 hover:bg-white/8 transition-all flex-shrink-0">
                  <Mic size={16} />
                </button>

                {/* Send button */}
                <motion.button
                  whileTap={{ scale: 0.92 }}
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  className={`
                    w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0
                    transition-all duration-200
                    ${input.trim() && !isStreaming
                      ? 'bg-gradient-to-br from-cyber-cyan to-cyber-violet text-white shadow-[0_0_15px_rgba(0,212,255,0.3)]'
                      : 'bg-white/8 text-white/25 cursor-not-allowed'
                    }
                  `}
                >
                  {isStreaming ? (
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Send size={15} />
                  )}
                </motion.button>
              </div>
              <p className="text-white/20 text-xs text-center mt-2">
                Les réponses IA peuvent contenir des erreurs. Vérifiez les informations importantes.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
