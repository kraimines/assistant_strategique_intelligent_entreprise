import React, { useRef, useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Send, Plus, MessageSquare, Zap, Mic,
  AlertTriangle, Trash2, Loader2, TrendingUp, ArrowRight,
} from 'lucide-react';
import AppShell from '../components/layout/AppShell';
import MessageBubble from '../components/Chat/MessageBubble';
import { useChat } from '../hooks/useChat';
import { useAuthStore } from '../stores/authStore';
import { chatHistoryApi } from '../api/client';
import { nanoid } from '../utils/nanoid';
import type { ChatMessage } from '../types';

/* ── Suggested prompts per role ─────────────────────────────────────────── */
const roleChips: Record<string, string[]> = {
  employee: [
    'Montre mes projets actifs',
    'Demander un congé la semaine prochaine',
    'Mon score de performance',
    'Heures travaillées ce mois',
  ],
  manager: [
    'Charge de travail équipe cette semaine',
    "Congés en attente d'approbation",
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

/* ── Predictive alert banners ───────────────────────────────────────────── */
const predictiveBanners = [
  { type: 'warning',  message: '3 projets à risque de dépassement de délai — Cliquez pour investiguer' },
  { type: 'critical', message: 'Client Tunisie Telecom: signaux de désengagement détectés' },
  { type: 'info',     message: "Pic de charge inhabituel dans l'équipe Engineering ce mois" },
];

interface ConvSummary {
  session_id:      string;
  title:           string;
  detected_domain: string | null;
  updated_at:      string;
}

/* ── Domain color dots ──────────────────────────────────────────────────── */
const domainDot: Record<string, string> = {
  hr:  '#10B981',
  crm: '#3B82F6',
  erp: '#F59E0B',
  rag: '#8B5CF6',
};

export default function Chat() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user }     = useAuthStore();
  const {
    messages, isStreaming, conversationId,
    sendMessage, loadConversation, clearMessages,
  } = useChat();

  const [input, setInput]           = useState('');
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [activeConvId, setActiveConvId]   = useState<string | null>(null);
  const [loadingConvId, setLoadingConvId] = useState<string | null>(null);
  const [showBanner, setShowBanner]       = useState(0);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef       = useRef<HTMLTextAreaElement>(null);
  const marketContext = searchParams.get('context')?.trim() || searchParams.get('q')?.trim();

  /* ── Auto-scroll ────────────────────────────────────────────────────── */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!marketContext || input) return;
    setInput(marketContext);
  }, [marketContext, input]);

  /* ── Load conversation list ─────────────────────────────────────────── */
  const refreshList = useCallback(async () => {
    try {
      const res = await chatHistoryApi.list();
      setConversations(res.data.conversations ?? []);
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => {
    if (!isStreaming && messages.length > 0) refreshList();
  }, [isStreaming, messages.length, refreshList]);

  /* ── Load a conversation ────────────────────────────────────────────── */
  const handleConvClick = useCallback(async (sessionId: string) => {
    if (loadingConvId || isStreaming) return;
    setLoadingConvId(sessionId);
    try {
      const res = await chatHistoryApi.getMessages(sessionId);
      const raw: { role: string; content: string; created_at: string }[] =
        res.data.messages ?? [];
      const history: ChatMessage[] = raw.map((m) => ({
        id:        nanoid(),
        role:      m.role as 'user' | 'assistant',
        content:   m.content,
        timestamp: new Date(m.created_at),
      }));
      loadConversation(sessionId, history);
      setActiveConvId(sessionId);
    } catch { /* ignore */ }
    finally { setLoadingConvId(null); }
  }, [loadingConvId, isStreaming, loadConversation]);

  /* ── Delete a conversation ──────────────────────────────────────────── */
  const handleDelete = useCallback(async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await chatHistoryApi.delete(sessionId);
      setConversations((prev) => prev.filter((c) => c.session_id !== sessionId));
      if (activeConvId === sessionId) {
        clearMessages();
        setActiveConvId(null);
      }
    } catch { /* ignore */ }
  }, [activeConvId, clearMessages]);

  /* ── New conversation ───────────────────────────────────────────────── */
  const handleNewChat = () => {
    clearMessages();
    setActiveConvId(null);
  };

  /* ── Send message ───────────────────────────────────────────────────── */
  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const text = input.trim();
    setInput('');
    setActiveConvId(conversationId);
    sendMessage(text);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const chips  = roleChips[user?.role || 'employee'];
  const banner = predictiveBanners[showBanner % predictiveBanners.length];

  /* ── Alert banner styles ────────────────────────────────────────────── */
  const bannerStyle: React.CSSProperties =
    banner.type === 'critical'
      ? { background: 'var(--danger-subtle)',  borderColor: 'rgba(239,68,68,0.25)',  color: '#DC2626' }
      : banner.type === 'warning'
      ? { background: 'var(--warning-subtle)', borderColor: 'rgba(245,158,11,0.25)', color: '#D97706' }
      : { background: 'var(--primary-subtle)', borderColor: 'rgba(59,130,246,0.20)', color: 'var(--primary)' };

  return (
    <AppShell title="Assistant IA">
      <div className="flex h-full overflow-hidden">

        {/* ════════════════════════════════════════════════════════════════
            LEFT: Conversations sidebar
            ════════════════════════════════════════════════════════════════ */}
        <aside
          className="w-60 flex-shrink-0 flex flex-col h-full"
          style={{
            borderRight: '1px solid var(--border-subtle)',
            background:  'var(--bg-base)',
          }}
        >
          {/* New chat button */}
          <div className="p-3">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200"
              style={{
                background:  'var(--primary)',
                color:       '#fff',
                boxShadow:   '0 2px 8px rgba(37,99,235,0.22)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary-dark)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'var(--primary)';
              }}
            >
              <Plus size={15} />
              Nouvelle conversation
            </button>
          </div>

          {/* Conversations list */}
          <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
            {conversations.length === 0 && (
              <p
                className="text-xs text-center mt-8 px-3"
                style={{ color: 'var(--text-faint)' }}
              >
                Aucune conversation enregistrée
              </p>
            )}

            {conversations.map((c) => {
              const isActive = activeConvId === c.session_id;
              return (
                <button
                  key={c.session_id}
                  onClick={() => handleConvClick(c.session_id)}
                  className="w-full text-left px-3 py-2.5 rounded-xl transition-all duration-150 group relative"
                  style={{
                    background: isActive ? 'var(--conv-active-bg)' : 'transparent',
                    color:      isActive ? 'var(--primary-dark)' : 'var(--text-secondary)',
                    border:     isActive
                      ? '1px solid var(--primary-muted)'
                      : '1px solid transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLButtonElement).style.background = 'var(--conv-hover-bg)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                    }
                  }}
                >
                  <div className="flex items-center gap-2 pr-6">
                    {loadingConvId === c.session_id ? (
                      <Loader2
                        size={12}
                        className="flex-shrink-0 animate-spin"
                        style={{ color: 'var(--primary)' }}
                      />
                    ) : (
                      <MessageSquare
                        size={12}
                        className="flex-shrink-0"
                        style={{ color: 'var(--text-faint)' }}
                      />
                    )}
                    <span className="text-xs truncate font-medium">{c.title || 'Conversation'}</span>
                  </div>

                  <div className="flex items-center gap-2 mt-1 pl-5">
                    {c.detected_domain && (
                      <span
                        className="flex items-center gap-1 text-[10px] font-semibold uppercase"
                        style={{ color: domainDot[c.detected_domain] ?? 'var(--text-faint)' }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ background: domainDot[c.detected_domain] ?? 'var(--text-faint)' }}
                        />
                        {c.detected_domain}
                      </span>
                    )}
                    <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      {new Date(c.updated_at).toLocaleDateString('fr-FR')}
                    </span>
                  </div>

                  {/* Delete on hover */}
                  <button
                    onClick={(e) => handleDelete(e, c.session_id)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded-lg transition-all"
                    style={{ color: 'var(--text-faint)' }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'var(--danger-subtle)';
                      (e.currentTarget as HTMLButtonElement).style.color = 'var(--danger)';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                      (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-faint)';
                    }}
                    title="Supprimer"
                  >
                    <Trash2 size={11} />
                  </button>
                </button>
              );
            })}
          </div>
        </aside>

        {/* ════════════════════════════════════════════════════════════════
            RIGHT: Chat main area
            ════════════════════════════════════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

          {/* Predictive banner */}
          <AnimatePresence>
            <motion.div
              key={showBanner}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm border-b cursor-pointer flex-shrink-0"
              style={{ ...bannerStyle, borderBottomColor: bannerStyle.borderColor }}
              onClick={() => setShowBanner((s) => s + 1)}
            >
              <div className="flex items-center gap-2.5">
                <AlertTriangle size={13} className="flex-shrink-0" />
                <span className="font-medium">{banner.message}</span>
              </div>
              <span
                className="text-xs flex-shrink-0"
                style={{ color: 'var(--text-faint)' }}
              >
                Suivant →
              </span>
            </motion.div>
          </AnimatePresence>

          {/* Messages area */}
          <div
            className="flex-1 overflow-y-auto px-6 py-6"
            style={{ background: 'var(--bg-base)' }}
          >
            {messages.length === 0 ? (
              /* ── Empty state ──────────────────────────────────────────── */
              <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
                {marketContext && (
                  <div
                    className="w-full max-w-2xl flex items-center justify-between gap-4 px-4 py-3 rounded-2xl border"
                    style={{
                      background: 'var(--bg-surface)',
                      borderColor: 'var(--border-subtle)',
                      boxShadow: 'var(--shadow-card)',
                    }}
                  >
                    <div className="text-left">
                      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--primary)' }}>
                        Contexte marché détecté
                      </p>
                      <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
                        Le champ de saisie a été préparé depuis `Market Analysis`.
                      </p>
                    </div>
                    <button
                      onClick={() => navigate('/market-analysis')}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold transition-all"
                      style={{ background: 'var(--primary-subtle)', color: 'var(--primary-dark)' }}
                    >
                      Ouvrir l'analyse
                      <ArrowRight size={14} />
                    </button>
                  </div>
                )}

                {/* Icon */}
                <motion.div
                  animate={{ y: [0, -6, 0] }}
                  transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
                  className="w-16 h-16 rounded-2xl flex items-center justify-center"
                  style={{
                    background: 'linear-gradient(135deg, #3B82F6, #14B8A6)',
                    boxShadow:  '0 8px 24px rgba(59,130,246,0.25)',
                  }}
                >
                  <Zap size={30} color="#fff" />
                </motion.div>

                {/* Heading */}
                <div>
                  <h2
                    className="text-xl font-bold mb-1.5"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    Comment puis-je vous aider ?
                  </h2>
                  <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                    Posez une question sur vos données RH, CRM ou ERP
                  </p>
                </div>

                {/* Suggested prompts */}
                <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                  {chips.map((chip) => (
                    <motion.button
                      key={chip}
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => { setInput(chip); inputRef.current?.focus(); }}
                      className="px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200"
                      style={{
                        background:  'var(--bg-surface)',
                        border:      '1px solid var(--border-subtle)',
                        color:       'var(--text-secondary)',
                        boxShadow:   'var(--shadow-card)',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-accent)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'var(--primary)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-subtle)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                      }}
                    >
                      {chip}
                    </motion.button>
                  ))}
                  <motion.button
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => navigate('/market-analysis')}
                    className="px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 inline-flex items-center gap-2"
                    style={{
                      background: 'var(--primary-subtle)',
                      border: '1px solid var(--primary-muted)',
                      color: 'var(--primary-dark)',
                    }}
                  >
                    <TrendingUp size={14} />
                    Aller vers l'analyse de marché
                  </motion.button>
                </div>
              </div>
            ) : (
              /* ── Messages list ────────────────────────────────────────── */
              <div className="max-w-3xl mx-auto">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* ── Input area ─────────────────────────────────────────────── */}
          <div
            className="px-6 py-4 flex-shrink-0"
            style={{
              borderTop:  '1px solid var(--border-subtle)',
              background: 'var(--bg-topbar)',
              backdropFilter: 'blur(16px)',
            }}
          >
            <div className="max-w-3xl mx-auto">
              <div
                className="flex items-end gap-3 rounded-2xl p-3 transition-all duration-200"
                style={{
                  background:  'var(--bg-surface)',
                  border:      `1px solid ${isStreaming ? 'var(--primary)' : 'var(--border-subtle)'}`,
                  boxShadow:   isStreaming
                    ? '0 0 0 3px rgba(59,130,246,0.10)'
                    : 'var(--shadow-card)',
                }}
              >
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Posez votre question… (Entrée pour envoyer, Maj+Entrée pour nouvelle ligne)"
                  disabled={isStreaming}
                  rows={1}
                  className="flex-1 bg-transparent text-sm focus:outline-none resize-none max-h-36 overflow-y-auto leading-relaxed py-1 chat-textarea"
                  style={{
                    color: 'var(--text-primary)',
                    fieldSizing: 'content',
                  } as React.CSSProperties}
                />

                {/* Mic button */}
                <button
                  className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 flex-shrink-0"
                  style={{ color: 'var(--text-faint)' }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-base)';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-faint)';
                  }}
                >
                  <Mic size={15} />
                </button>

                {/* Send button */}
                <motion.button
                  whileTap={{ scale: 0.93 }}
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all duration-200"
                  style={
                    input.trim() && !isStreaming
                      ? {
                          background: 'linear-gradient(135deg, #3B82F6, #2563EB)',
                          boxShadow:  '0 2px 8px rgba(37,99,235,0.30)',
                          color:      '#fff',
                        }
                      : {
                          background: 'var(--bg-base)',
                          color:      'var(--text-faint)',
                          cursor:     'not-allowed',
                        }
                  }
                >
                  {isStreaming ? (
                    <div
                      className="w-3.5 h-3.5 border-2 border-t-transparent rounded-full animate-spin"
                      style={{ borderColor: '#3B82F6', borderTopColor: 'transparent' }}
                    />
                  ) : (
                    <Send size={14} />
                  )}
                </motion.button>
              </div>

              {/* Disclaimer */}
              <p
                className="text-xs text-center mt-2"
                style={{ color: 'var(--text-faint)' }}
              >
                Les réponses IA peuvent contenir des erreurs. Vérifiez les informations importantes.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
