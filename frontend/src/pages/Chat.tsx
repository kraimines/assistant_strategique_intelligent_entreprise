import React, { useRef, useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Plus, MessageSquare, Zap, Mic, AlertTriangle, Trash2, Loader2 } from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import MessageBubble from '../components/chat/MessageBubble';
import { useChat } from '../hooks/useChat';
import { useAuthStore } from '../stores/authStore';
import { chatHistoryApi } from '../api/client';
import { nanoid } from '../utils/nanoid';
import type { ChatMessage } from '../types';

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
  session_id: string;
  title: string;
  detected_domain: string | null;
  updated_at: string;
}

export default function Chat() {
  const { user } = useAuthStore();
  const { messages, isStreaming, conversationId, sendMessage, loadConversation, clearMessages } = useChat();

  const [input, setInput] = useState('');
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [loadingConvId, setLoadingConvId] = useState<string | null>(null);
  const [showBanner, setShowBanner] = useState(0);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── Scroll to bottom on new message ──────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Load conversation list on mount ──────────────────────────────────────
  const refreshList = useCallback(async () => {
    try {
      const res = await chatHistoryApi.list();
      setConversations(res.data.conversations ?? []);
    } catch {
      // silently ignore — history is non-critical
    }
  }, []);

  useEffect(() => { refreshList(); }, [refreshList]);

  // ── Refresh list after streaming ends ────────────────────────────────────
  useEffect(() => {
    if (!isStreaming && messages.length > 0) refreshList();
  }, [isStreaming, messages.length, refreshList]);

  // ── Click a conversation in the sidebar ──────────────────────────────────
  const handleConvClick = useCallback(async (sessionId: string) => {
    if (loadingConvId || isStreaming) return;
    setLoadingConvId(sessionId);
    try {
      const res = await chatHistoryApi.getMessages(sessionId);
      const raw: { role: string; content: string; created_at: string }[] =
        res.data.messages ?? [];
      const history: ChatMessage[] = raw.map((m) => ({
        id: nanoid(),
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: new Date(m.created_at),
      }));
      loadConversation(sessionId, history);
      setActiveConvId(sessionId);
    } catch {
      // ignore
    } finally {
      setLoadingConvId(null);
    }
  }, [loadingConvId, isStreaming, loadConversation]);

  // ── Delete a conversation ─────────────────────────────────────────────────
  const handleDelete = useCallback(async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await chatHistoryApi.delete(sessionId);
      setConversations((prev) => prev.filter((c) => c.session_id !== sessionId));
      if (activeConvId === sessionId) {
        clearMessages();
        setActiveConvId(null);
      }
    } catch {
      // ignore
    }
  }, [activeConvId, clearMessages]);

  // ── New conversation ──────────────────────────────────────────────────────
  const handleNewChat = () => {
    clearMessages();
    setActiveConvId(null);
  };

  // ── Send ──────────────────────────────────────────────────────────────────
  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const text = input.trim();
    setInput('');
    // Use the current conversationId from the hook (tracks active session)
    setActiveConvId(conversationId);
    sendMessage(text);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const chips = roleChips[user?.role || 'employee'];
  const banner = predictiveBanners[showBanner % predictiveBanners.length];

  const domainColor: Record<string, string> = {
    hr:  'text-emerald-400',
    crm: 'text-cyber-cyan',
    erp: 'text-amber-400',
    rag: 'text-violet-400',
  };

  return (
    <AppShell title="Assistant IA">
      <div className="flex h-full">

        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <aside
          className="w-64 flex-shrink-0 flex flex-col h-full"
          style={{ borderRight: '1px solid var(--border-subtle)', background: 'var(--bg-overlay)' }}
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
            {conversations.length === 0 && (
              <p className="text-xs text-center mt-6 px-3" style={{ color: 'var(--text-muted)' }}>
                Aucune conversation enregistrée
              </p>
            )}
            {conversations.map((c) => (
              <button
                key={c.session_id}
                onClick={() => handleConvClick(c.session_id)}
                className="w-full text-left px-3 py-2.5 rounded-xl transition-all group relative"
                style={{
                  background: activeConvId === c.session_id ? 'var(--conv-active-bg)' : undefined,
                  color: activeConvId === c.session_id ? 'var(--text-primary)' : 'var(--text-secondary)',
                }}
              >
                <div className="flex items-center gap-2 pr-6">
                  {loadingConvId === c.session_id ? (
                    <Loader2 size={13} className="flex-shrink-0 text-cyber-cyan animate-spin" />
                  ) : (
                    <MessageSquare size={13} className="flex-shrink-0 text-white/30" />
                  )}
                  <span className="text-xs truncate">{c.title || 'Conversation'}</span>
                </div>
                <div className="flex items-center gap-2 mt-1 pl-5">
                  {c.detected_domain && (
                    <span className={`text-[10px] font-medium uppercase ${domainColor[c.detected_domain] ?? 'text-white/30'}`}>
                      {c.detected_domain}
                    </span>
                  )}
                  <span className="text-white/25 text-[10px]">
                    {new Date(c.updated_at).toLocaleDateString('fr-FR')}
                  </span>
                </div>

                {/* Delete button (visible on hover) */}
                <button
                  onClick={(e) => handleDelete(e, c.session_id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-red-500/20 hover:text-red-400 text-white/30 transition-all"
                  title="Supprimer"
                >
                  <Trash2 size={12} />
                </button>
              </button>
            ))}
          </div>
        </aside>

        {/* ── Main chat area ───────────────────────────────────────────────── */}
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
                  <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>Comment puis-je vous aider ?</h2>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Posez une question sur vos données RH, CRM ou ERP</p>
                </div>
                <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                  {chips.map((chip) => (
                    <motion.button
                      key={chip}
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => { setInput(chip); inputRef.current?.focus(); }}
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
          <div className="px-6 py-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <div className="max-w-3xl mx-auto">
              <div
                className="flex items-end gap-3 rounded-2xl p-3"
                style={{
                  background: 'var(--bg-overlay-input)',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid var(--input-border)',
                  boxShadow: isStreaming ? '0 0 20px rgba(0,212,255,0.1)' : 'none',
                  transition: 'box-shadow 0.3s, background 0.3s',
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
                  className="flex-1 bg-transparent text-sm focus:outline-none resize-none max-h-36 overflow-y-auto leading-relaxed py-1 chat-textarea"
                  style={{ color: 'var(--text-primary)', fieldSizing: 'content' } as React.CSSProperties}
                />
                <button className="w-9 h-9 rounded-xl flex items-center justify-center text-white/30 hover:text-white/60 hover:bg-white/8 transition-all flex-shrink-0">
                  <Mic size={16} />
                </button>
                <motion.button
                  whileTap={{ scale: 0.92 }}
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  className={`
                    w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all duration-200
                    ${input.trim() && !isStreaming
                      ? 'bg-gradient-to-br from-cyber-cyan to-cyber-violet text-white shadow-[0_0_15px_rgba(0,212,255,0.3)]'
                      : 'bg-white/8 text-white/25 cursor-not-allowed'
                    }
                  `}
                >
                  {isStreaming
                    ? <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Send size={15} />
                  }
                </motion.button>
              </div>
              <p className="text-xs text-center mt-2" style={{ color: 'var(--text-muted)' }}>
                Les réponses IA peuvent contenir des erreurs. Vérifiez les informations importantes.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
