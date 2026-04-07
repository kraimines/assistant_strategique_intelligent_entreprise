import { useState, useRef, useCallback } from 'react';
import { useAuthStore } from '../stores/authStore';
import type { ChatMessage, AgentType } from '../types';
import { nanoid } from '../utils/nanoid';
import { API_BASE_URL } from '../api/client';

export function useChat() {
  const { token } = useAuthStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<AgentType | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string, conversationId?: string) => {
      if (!text.trim() || isStreaming) return;

      const userMsg: ChatMessage = {
        id: nanoid(),
        role: 'user',
        content: text,
        timestamp: new Date(),
      };
      const assistantMsg: ChatMessage = {
        id: nanoid(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);
      setCurrentAgent(null);

      abortRef.current = new AbortController();

      try {
        // Use streaming endpoint with fetch + ReadableStream
        const res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token || 'dev-token'}`,
          },
          body: JSON.stringify({
            message: text,
            ...(conversationId ? { conversation_id: conversationId } : {}),
          }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) {
          const errText = await res.text().catch(() => `HTTP ${res.status}`);
          let detail = `Erreur ${res.status}`;
          try { detail = JSON.parse(errText).detail || detail; } catch { /* ignore */ }
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last?.isStreaming) return prev;
            return [...prev.slice(0, -1), { ...last, content: detail, isStreaming: false }];
          });
          setIsStreaming(false);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          throw new Error('No readable stream');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        const processLines = (lines: string[]) => {
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) continue;
            const raw = trimmed.slice(5).trim();
            if (!raw || raw === '[DONE]') continue;
            try {
              const event = JSON.parse(raw);
              if (event.type === 'token' && event.content) {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (!last?.isStreaming) return prev;
                  return [...prev.slice(0, -1), { ...last, content: last.content + event.content }];
                });
              } else if (event.type === 'agent' && event.agent) {
                setCurrentAgent(event.agent as AgentType);
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (!last?.isStreaming) return prev;
                  return [...prev.slice(0, -1), { ...last, agent: event.agent }];
                });
              } else if (event.type === 'done') {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (!last?.isStreaming) return prev;
                  return [...prev.slice(0, -1), { ...last, isStreaming: false }];
                });
                setIsStreaming(false);
              } else if (event.type === 'error') {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (!last?.isStreaming) return prev;
                  return [...prev.slice(0, -1), { ...last, content: event.message || 'Erreur agent.', isStreaming: false }];
                });
                setIsStreaming(false);
              }
            } catch { /* ignore malformed */ }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          processLines(lines);
        }

        // Process remaining buffer
        if (buffer.trim()) processLines([buffer]);

        // Ensure streaming is done
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (!last?.isStreaming) return prev;
          return [...prev.slice(0, -1), { ...last, isStreaming: false }];
        });
        setIsStreaming(false);

      } catch (err: unknown) {
        const isAbort = (err as { name?: string })?.name === 'AbortError';
        if (isAbort) return;

        console.error('Chat error:', err);

        // Fallback: try non-streaming endpoint
        try {
          const res2 = await fetch(`${API_BASE_URL}/api/v1/chat`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token || 'dev-token'}`,
            },
            body: JSON.stringify({ message: text }),
          });
          const data = await res2.json();
          const reply = data.reply || data.detail || 'Erreur inconnue.';
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last?.isStreaming) return prev;
            return [...prev.slice(0, -1), { ...last, content: reply, isStreaming: false }];
          });
        } catch {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last?.isStreaming) return prev;
            return [
              ...prev.slice(0, -1),
              { ...last, content: 'Impossible de contacter le serveur. Vérifiez que le backend tourne sur le port 8001.', isStreaming: false },
            ];
          });
        }
        setIsStreaming(false);
      }
    },
    [token, isStreaming]
  );

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    setCurrentAgent(null);
  }, []);

  return { messages, isStreaming, currentAgent, sendMessage, clearMessages };
}
