import { useState } from 'react';
import { motion } from 'framer-motion';
import { Calendar, Clock, Users, Link2, CheckCircle2, Copy, Check, Video } from 'lucide-react';
import type { MeetingData } from '../../types/meetingTypes';

export type { MeetingData };

interface MeetingCardProps {
  meeting: MeetingData;
}

export default function MeetingCard({ meeting }: MeetingCardProps) {
  const [copied, setCopied] = useState(false);
  const [sent, setSent]     = useState(false);

  const handleCopyLink = () => {
    navigator.clipboard.writeText(meeting.link).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendInvites = () => {
    setSent(true);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-2xl overflow-hidden text-sm"
      style={{
        border:    '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-card)',
        background: 'var(--bg-surface)',
        maxWidth: 460,
      }}
    >
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div
        className="px-5 py-4"
        style={{
          background: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
          color: '#fff',
        }}
      >
        <div className="flex items-center gap-2 mb-1 opacity-80 text-xs font-medium uppercase tracking-wide">
          <Video size={12} />
          Réunion planifiée
        </div>
        <div className="font-bold text-base leading-tight">{meeting.title}</div>
        <div className="text-xs opacity-75 mt-1">{meeting.project}</div>
      </div>

      {/* ── Meta info ────────────────────────────────────────────────── */}
      <div className="px-5 py-3 flex flex-col gap-2.5" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2.5" style={{ color: 'var(--text-secondary)' }}>
          <Calendar size={14} style={{ color: 'var(--primary)', flexShrink: 0 }} />
          <span className="font-medium">{meeting.date}</span>
        </div>
        <div className="flex items-center gap-2.5" style={{ color: 'var(--text-secondary)' }}>
          <Clock size={14} style={{ color: 'var(--primary)', flexShrink: 0 }} />
          <span>{meeting.time}</span>
        </div>
        <div className="flex items-center gap-2.5" style={{ color: 'var(--text-secondary)' }}>
          <Link2 size={14} style={{ color: 'var(--primary)', flexShrink: 0 }} />
          <a
            href={meeting.link}
            target="_blank"
            rel="noreferrer"
            className="truncate font-mono text-xs hover:underline"
            style={{ color: 'var(--primary)' }}
          >
            {meeting.link}
          </a>
          <button
            onClick={handleCopyLink}
            className="ml-auto p-1 rounded-lg flex-shrink-0 transition-colors"
            style={{ color: copied ? 'var(--success)' : 'var(--text-faint)' }}
            title="Copier le lien"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        </div>
      </div>

      {/* ── Participants ─────────────────────────────────────────────── */}
      <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div
          className="flex items-center gap-1.5 mb-2.5 text-xs font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-faint)' }}
        >
          <Users size={11} />
          Participants ({meeting.participants.length})
        </div>
        <div className="flex flex-col gap-2">
          {meeting.participants.map((p) => (
            <div key={p.email} className="flex items-center gap-2.5">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                style={{
                  background: stringToColor(p.name),
                  color: '#fff',
                }}
              >
                {p.avatar}
              </div>
              <div className="min-w-0">
                <div className="font-medium text-xs leading-tight truncate" style={{ color: 'var(--text-primary)' }}>
                  {p.name}
                </div>
                <div className="text-[10px] truncate" style={{ color: 'var(--text-faint)' }}>
                  {p.role} · {p.email}
                </div>
              </div>
              {sent && (
                <CheckCircle2
                  size={13}
                  className="ml-auto flex-shrink-0"
                  style={{ color: 'var(--success)' }}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Action ───────────────────────────────────────────────────── */}
      <div className="px-5 py-3">
        {sent ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold"
            style={{ background: 'var(--success-subtle)', color: 'var(--success)' }}
          >
            <CheckCircle2 size={14} />
            Invitations envoyées à tous les participants
          </motion.div>
        ) : (
          <button
            onClick={handleSendInvites}
            className="w-full py-2.5 rounded-xl text-xs font-semibold transition-all duration-200"
            style={{
              background: 'linear-gradient(135deg, #2563eb, #3b82f6)',
              color: '#fff',
              boxShadow: '0 2px 8px rgba(37,99,235,0.25)',
            }}
          >
            Envoyer les invitations
          </button>
        )}
      </div>
    </motion.div>
  );
}

function stringToColor(str: string): string {
  const palette = ['#2563eb','#7c3aed','#db2777','#059669','#d97706','#dc2626','#0891b2'];
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}
