import { useCallback, useEffect, useRef, useState } from 'react';
import { createSession, deleteSession, getSession, listSessions, streamChat } from '../api/chat';
import type { AgentEvent, Message, Session } from '../types';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [toast, setToast] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const refreshSessions = useCallback(async () => setSessions(await listSessions()), []);
  useEffect(() => { refreshSessions().catch(() => undefined); }, [refreshSessions]);
  const showToast = useCallback((text: string) => { setToast(text); window.setTimeout(() => setToast(''), 1800); }, []);

  const run = useCallback(async (sessionId: string, message: string) => {
    const controller = new AbortController();
    abortRef.current = controller; setIsStreaming(true); setStreamingContent('');
    let fullText = '';
    try {
      await streamChat(sessionId, message, controller.signal, (event: AgentEvent) => {
        if (event.type === 'text_delta') { fullText += event.data.content; setStreamingContent(fullText); }
        if (event.type === 'tool_started') showToast(`正在调用工具：${event.data.name}`);
        if (event.type === 'error') throw new Error(event.data.message);
      });
      if (fullText) setMessages(prev => [...prev, { role: 'assistant', content: fullText }]);
      await refreshSessions();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) showToast(error instanceof Error ? error.message : '发送失败');
    } finally { setIsStreaming(false); setStreamingContent(''); abortRef.current = null; }
  }, [refreshSessions, showToast]);

  const handleSendWithSession = useCallback(async (message: string) => {
    if (!message.trim() || isStreaming) return;
    let id = currentSessionId;
    if (!id) { const session = await createSession(message.slice(0, 30)); id = session.id; setCurrentSessionId(id); }
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    await run(id, message);
  }, [currentSessionId, isStreaming, run]);

  const handleSwitchSession = useCallback(async (id: string) => { const data = await getSession(id); setCurrentSessionId(id); setMessages(data.messages); }, []);
  const handleDeleteSession = useCallback(async (id: string) => { await deleteSession(id); if (id === currentSessionId) { setCurrentSessionId(''); setMessages([]); } await refreshSessions(); }, [currentSessionId, refreshSessions]);
  const handleNewChat = useCallback(() => { abortRef.current?.abort(); setCurrentSessionId(''); setMessages([]); setStreamingContent(''); }, []);
  const handleStop = useCallback(() => abortRef.current?.abort(), []);
  const handleCopy = useCallback((text: string) => { navigator.clipboard.writeText(text).then(() => showToast('已复制')); }, [showToast]);
  const handleRegenerate = useCallback(() => showToast('当前版本暂不支持重新生成'), [showToast]);
  const handleEditMessage = useCallback((_index: number, _content: string) => showToast('当前版本暂不支持编辑历史消息'), [showToast]);

  return { messages, isStreaming, streamingContent, toast, currentSessionId, sessions, handleSendWithSession, handleRegenerate, handleStop, handleNewChat, handleCopy, handleEditMessage, handleSwitchSession, handleDeleteSession };
}
