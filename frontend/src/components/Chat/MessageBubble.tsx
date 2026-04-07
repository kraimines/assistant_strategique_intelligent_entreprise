import { useState } from 'react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, ThumbsUp, ThumbsDown, Check } from 'lucide-react';
import { AgentBadge } from '../ui/Badge';
import type { ChatMessage } from '../../types';

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [reaction, setReaction] = useState<'up' | 'down' | null>(null);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, x: 20, y: 8 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        className="flex justify-end mb-4"
      >
        <div
          className="max-w-[75%] px-5 py-3.5 rounded-2xl rounded-tr-md text-sm text-white leading-relaxed"
          style={{
            background: 'linear-gradient(135deg, rgba(0,212,255,0.2), rgba(124,58,237,0.2))',
            border: '1px solid rgba(0,212,255,0.25)',
          }}
        >
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -20, y: 8 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      className="flex flex-col mb-6 max-w-[85%]"
    >
      {/* Agent badge */}
      {message.agent && (
        <div className="mb-2">
          <AgentBadge agent={message.agent} />
        </div>
      )}

      {/* Message bubble */}
      <div
        className="px-5 py-4 rounded-2xl rounded-tl-md text-sm text-white/85 leading-relaxed"
        style={{
          background: 'rgba(18, 18, 30, 0.85)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        {message.isStreaming && message.content === '' ? (
          <div className="flex gap-1 items-center py-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.2 }}
                className="w-1.5 h-1.5 rounded-full bg-cyber-cyan"
              />
            ))}
          </div>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            {message.isStreaming && (
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                className="inline-block w-0.5 h-4 bg-cyber-cyan ml-0.5 align-middle"
              />
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      {!message.isStreaming && message.content && (
        <div className="flex items-center gap-2 mt-2 ml-1">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-white/30 hover:text-white/70 text-xs transition-colors"
          >
            {copied ? <Check size={13} className="text-cyber-emerald" /> : <Copy size={13} />}
            {copied ? 'Copié' : 'Copier'}
          </button>
          <span className="text-white/15">|</span>
          <button
            onClick={() => setReaction('up')}
            className={`transition-colors ${reaction === 'up' ? 'text-cyber-emerald' : 'text-white/30 hover:text-white/60'}`}
          >
            <ThumbsUp size={13} />
          </button>
          <button
            onClick={() => setReaction('down')}
            className={`transition-colors ${reaction === 'down' ? 'text-red-400' : 'text-white/30 hover:text-white/60'}`}
          >
            <ThumbsDown size={13} />
          </button>
        </div>
      )}
    </motion.div>
  );
}
