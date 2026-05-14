import { useState } from 'react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, ThumbsUp, ThumbsDown, Check, FileDown } from 'lucide-react';
import { AgentBadge } from '../ui/Badge';
import type { ChatMessage } from '../../types';
import MeetingCard from './MeetingCard';

interface MessageBubbleProps {
  message: ChatMessage;
}

function markdownToHtml(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  let inTable = false;
  let tableRowCount = 0;
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Inline: bold
    line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Heading 1
    if (/^# (.+)/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h1>${line.replace(/^# /, '')}</h1>`);
      continue;
    }
    // Heading 2
    if (/^## (.+)/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      const num = line.match(/^## (\d+)\./)?.[1];
      const label = line.replace(/^## /, '');
      out.push(`<h2 ${num ? `data-num="${num}"` : ''}>${label}</h2>`);
      continue;
    }
    // Heading 3
    if (/^### (.+)/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3>${line.replace(/^### /, '')}</h3>`);
      continue;
    }
    // HR
    if (/^---+$/.test(line.trim())) {
      if (inList) { out.push('</ul>'); inList = false; }
      if (inTable) { out.push('</tbody></table>'); inTable = false; tableRowCount = 0; }
      out.push('<hr/>');
      continue;
    }
    // Table row
    if (line.trim().startsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      // Separator row
      if (cells.every(c => /^[-:]+$/.test(c))) continue;
      if (!inTable) {
        if (inList) { out.push('</ul>'); inList = false; }
        out.push('<table><thead><tr>');
        cells.forEach(c => out.push(`<th>${c}</th>`));
        out.push('</tr></thead><tbody>');
        inTable = true;
        tableRowCount = 0;
      } else {
        const cls = tableRowCount % 2 === 0 ? ' class="even"' : '';
        out.push(`<tr${cls}>`);
        cells.forEach((c, idx) => {
          const align = idx === cells.length - 1 ? ' style="text-align:right"' : '';
          out.push(`<td${align}>${c}</td>`);
        });
        out.push('</tr>');
        tableRowCount++;
      }
      continue;
    } else if (inTable) {
      out.push('</tbody></table>');
      inTable = false;
      tableRowCount = 0;
    }
    // List item
    if (/^- (.+)/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      const content = line.replace(/^- /, '');
      // KPI line: "- **Label:** value"
      const kpiMatch = content.match(/^<strong>(.+?)<\/strong>\s*(.+)/);
      if (kpiMatch) {
        out.push(`<li class="kpi-item"><span class="kpi-label">${kpiMatch[1]}</span><span class="kpi-value">${kpiMatch[2]}</span></li>`);
      } else {
        out.push(`<li>${content}</li>`);
      }
      continue;
    } else if (inList) {
      out.push('</ul>');
      inList = false;
    }
    // Alert line
    if (line.includes('⚠') || line.toLowerCase().includes('alerte')) {
      out.push(`<div class="alert">${line}</div>`);
      continue;
    }
    // Meta line (bold key: value at start)
    if (/^\*\*[^*]+\*\*\s*:/.test(lines[i])) {
      out.push(`<p class="meta">${line}</p>`);
      continue;
    }
    // Normal paragraph
    if (line.trim()) {
      out.push(`<p>${line}</p>`);
    }
  }

  if (inList) out.push('</ul>');
  if (inTable) out.push('</tbody></table>');
  return out.join('\n');
}

function downloadReportAsPdf(content: string) {
  const now = new Date();
  const dateStr = now.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });
  const body = markdownToHtml(content);

  const printWindow = window.open('', '_blank');
  if (!printWindow) return;

  printWindow.document.write(`<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <title>Rapport Talan — ${dateStr}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    @page { margin: 1.8cm 2cm; size: A4; }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
      font-size: 12px;
      color: #1e293b;
      line-height: 1.65;
      background: #fff;
    }

    /* ── Cover header ── */
    .report-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 18px 24px;
      background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
      border-radius: 8px;
      margin-bottom: 28px;
      color: white;
    }
    .report-header .brand { font-size: 18px; font-weight: 700; letter-spacing: .5px; }
    .report-header .brand span { opacity: .7; font-weight: 400; font-size: 13px; margin-left: 8px; }
    .report-header .date { font-size: 11px; opacity: .85; text-align: right; }

    /* ── h1 (report title) ── */
    h1 {
      font-size: 20px;
      font-weight: 700;
      color: #1e3a8a;
      margin-bottom: 6px;
      line-height: 1.3;
    }

    /* ── Section headings ── */
    h2 {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(90deg, #2563eb, #3b82f6);
      padding: 7px 14px;
      border-radius: 5px;
      margin: 22px 0 12px;
      letter-spacing: .3px;
    }
    h3 {
      font-size: 12px;
      font-weight: 600;
      color: #1e40af;
      margin: 14px 0 6px;
    }

    hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }

    p { margin-bottom: 8px; }
    p.meta { font-size: 11.5px; color: #475569; }
    p.meta strong { color: #1e3a8a; }

    /* ── Table ── */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0 18px;
      font-size: 11px;
      border-radius: 6px;
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }
    thead tr { background: #1e40af; }
    th {
      color: #fff;
      padding: 9px 11px;
      text-align: left;
      font-weight: 600;
      font-size: 11px;
      letter-spacing: .3px;
    }
    td {
      padding: 8px 11px;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
    }
    tr.even td { background: #f8fafc; }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: #eff6ff; }

    /* ── KPI list ── */
    ul { list-style: none; padding: 0; margin: 8px 0 14px; }
    li { padding: 5px 0; border-bottom: 1px solid #f1f5f9; font-size: 11.5px; }
    li:last-child { border-bottom: none; }
    li.kpi-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 7px 12px;
      background: #f8fafc;
      border-radius: 5px;
      margin-bottom: 5px;
      border-bottom: none;
    }
    .kpi-label { font-weight: 600; color: #334155; }
    .kpi-value {
      font-weight: 700;
      color: #1e40af;
      background: #eff6ff;
      padding: 2px 10px;
      border-radius: 20px;
      font-size: 11px;
    }

    /* ── Alerts ── */
    .alert {
      background: #fff7ed;
      border-left: 4px solid #f97316;
      padding: 9px 14px;
      border-radius: 0 5px 5px 0;
      margin: 8px 0;
      font-size: 11.5px;
      color: #7c2d12;
    }
    .alert strong { color: #c2410c; }

    strong { color: #1e3a8a; }

    /* ── Footer ── */
    .footer {
      margin-top: 36px;
      padding-top: 12px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #94a3b8;
    }

    /* ── Print button (hidden on print) ── */
    .no-print {
      text-align: center;
      margin: 28px 0 10px;
    }
    .no-print button {
      padding: 11px 32px;
      background: linear-gradient(135deg, #1e40af, #2563eb);
      color: white;
      border: none;
      border-radius: 7px;
      cursor: pointer;
      font-size: 13px;
      font-family: inherit;
      font-weight: 600;
      box-shadow: 0 2px 8px rgba(37,99,235,.35);
      transition: opacity .2s;
    }
    .no-print button:hover { opacity: .9; }

    @media print {
      .no-print { display: none; }
      body { font-size: 11px; }
      h1 { font-size: 18px; }
      h2 { font-size: 12px; }
    }
  </style>
</head>
<body>
  <div class="report-header">
    <div class="brand">Talan <span>Intelligence Assistant</span></div>
    <div class="date">Généré le ${dateStr}<br/>Confidentiel — usage interne</div>
  </div>

  ${body}

  <div class="footer">
    <span>Talan Group — Rapport généré automatiquement</span>
    <span>${dateStr}</span>
  </div>

  <div class="no-print">
    <button onclick="window.print()">⬇ Enregistrer en PDF / Imprimer</button>
  </div>
</body>
</html>`);

  printWindow.document.close();
  printWindow.focus();
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied]   = useState(false);
  const [reaction, setReaction] = useState<'up' | 'down' | null>(null);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /* ── User bubble ──────────────────────────────────────────────────────── */
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, x: 16, y: 6 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        transition={{ duration: 0.28, ease: 'easeOut' }}
        className="flex justify-end mb-4"
      >
        <div
          className="max-w-[75%] px-5 py-3.5 rounded-2xl rounded-tr-md text-sm leading-relaxed"
          style={{
            background:  'linear-gradient(135deg, #EFF6FF, #DBEAFE)',
            border:      '1px solid #BFDBFE',
            color:       'var(--text-primary)',
          }}
        >
          {message.content}
        </div>
      </motion.div>
    );
  }

  /* ── Assistant bubble ─────────────────────────────────────────────────── */
  return (
    <motion.div
      initial={{ opacity: 0, x: -16, y: 6 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      className="flex flex-col mb-6 max-w-[88%]"
    >
      {/* Agent badge */}
      {message.agent && (
        <div className="mb-2">
          <AgentBadge agent={message.agent} />
        </div>
      )}

      {/* Bubble */}
      <div
        className="px-5 py-4 rounded-2xl rounded-tl-md text-sm leading-relaxed"
        style={{
          background: 'var(--bg-surface)',
          border:     '1px solid var(--border-subtle)',
          boxShadow:  'var(--shadow-card)',
          color:      'var(--text-primary)',
        }}
      >
        {/* Typing indicator */}
        {message.isStreaming && message.content === '' ? (
          <div className="flex gap-1.5 items-center py-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.22 }}
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: 'var(--primary)' }}
              />
            ))}
          </div>
        ) : (
          <div className="markdown-body">
            {/* Meeting card */}
            {message.meetingData && !message.isStreaming && (
              <div className="mb-3">
                <MeetingCard meeting={message.meetingData} />
              </div>
            )}

            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div style={{ overflowX: 'auto', width: '100%', margin: '0.75em 0' }}>
                    <table>{children}</table>
                  </div>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>

            {/* Streaming cursor */}
            {message.isStreaming && (
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                className="inline-block w-0.5 h-4 ml-0.5 align-middle rounded-full"
                style={{ background: 'var(--primary)' }}
              />
            )}
          </div>
        )}
      </div>

      {/* Actions bar */}
      {!message.isStreaming && message.content && (
        <div
          className="flex items-center gap-2.5 mt-2 ml-1 text-xs flex-wrap"
          style={{ color: 'var(--text-faint)' }}
        >
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 transition-colors hover:text-primary"
            style={{ color: copied ? 'var(--success)' : 'var(--text-faint)' }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copié' : 'Copier'}
          </button>

          <span style={{ color: 'var(--border-strong)' }}>·</span>

          <button
            onClick={() => setReaction('up')}
            className="p-1 rounded-lg transition-all"
            style={{
              color:      reaction === 'up' ? 'var(--success)' : 'var(--text-faint)',
              background: reaction === 'up' ? 'var(--success-subtle)' : 'transparent',
            }}
          >
            <ThumbsUp size={12} />
          </button>

          <button
            onClick={() => setReaction('down')}
            className="p-1 rounded-lg transition-all"
            style={{
              color:      reaction === 'down' ? 'var(--danger)' : 'var(--text-faint)',
              background: reaction === 'down' ? 'var(--danger-subtle)' : 'transparent',
            }}
          >
            <ThumbsDown size={12} />
          </button>

          {message.isReport && (
            <>
              <span style={{ color: 'var(--border-strong)' }}>·</span>
              <button
                onClick={() => downloadReportAsPdf(message.content)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all font-medium"
                style={{
                  color:      'var(--primary)',
                  background: 'var(--primary-subtle, #eff6ff)',
                  border:     '1px solid var(--primary-muted, #bfdbfe)',
                }}
              >
                <FileDown size={12} />
                Télécharger PDF
              </button>
            </>
          )}
        </div>
      )}
    </motion.div>
  );
}
