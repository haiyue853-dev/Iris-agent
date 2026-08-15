import { useCallback, useEffect, useRef, useState } from 'react';
import { createSession, deleteSession, getSession, listSessions } from '../api/chat';
import { cancelTask, createTask, getTask, resolveTaskApproval } from '../api/tasks';
import type { AgentEvent, Message, Session, TaskStatus } from '../types';

const TERMINAL_TASK_STATUSES = new Set<TaskStatus>(['completed', 'failed', 'stopped']);

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent] = useState('');
  const [toast, setToast] = useState('');
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<Extract<AgentEvent, { type: 'tool_approval_requested' }>['data'] | null>(null);
  const [currentTaskStatus, setCurrentTaskStatus] = useState<TaskStatus | null>(null);
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [approvalCallId, setApprovalCallId] = useState<string | null>(null);
  const currentSessionRef = useRef('');
  const currentTaskRef = useRef<string | null>(null);
  const pollersRef = useRef(new Map<string, number>());

  const refreshSessions = useCallback(async () => setSessions(await listSessions()), []);
  useEffect(() => { refreshSessions().catch(() => undefined); }, [refreshSessions]);
  const showToast = useCallback((text: string) => { setToast(text); window.setTimeout(() => setToast(''), 1800); }, []);

  useEffect(() => { currentSessionRef.current = currentSessionId; }, [currentSessionId]);
  useEffect(() => { currentTaskRef.current = currentTaskId; }, [currentTaskId]);
  useEffect(() => () => { pollersRef.current.forEach((timer) => window.clearInterval(timer)); pollersRef.current.clear(); }, []);

  const pollTask = useCallback(async (taskId: string, sessionId: string) => {
    try {
      const task = await getTask(taskId);
      if (currentTaskRef.current === taskId) {
        setCurrentTaskStatus(task.status);
        setQueuePosition(task.queue_position ?? null);
        setApprovalCallId(task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null);
        setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
      }
      if (!TERMINAL_TASK_STATUSES.has(task.status)) return;
      const timer = pollersRef.current.get(taskId);
      if (timer !== undefined) window.clearInterval(timer);
      pollersRef.current.delete(taskId);
      if (task.status === 'completed' && currentSessionRef.current === sessionId) {
        const session = await getSession(sessionId);
        if (currentSessionRef.current === sessionId) setMessages(session.messages);
      }
      if (task.status === 'failed') showToast('任务执行失败');
      if (task.status === 'stopped') showToast('任务已停止');
      await refreshSessions();
    } catch (error) {
      showToast(error instanceof Error ? error.message : '任务状态查询失败');
    }
  }, [refreshSessions, showToast]);

  const startPolling = useCallback((taskId: string, sessionId: string) => {
    const timer = window.setInterval(() => { void pollTask(taskId, sessionId); }, 1000);
    pollersRef.current.set(taskId, timer);
  }, [pollTask]);

  const resolvePendingApproval = useCallback(async (callId: string, approved: boolean) => {
    if (!currentTaskId || currentTaskStatus !== 'awaiting_approval' || approvalCallId !== callId) return;
    try {
      const task = await resolveTaskApproval(currentTaskId, callId, approved);
      setCurrentTaskStatus(task.status);
      setQueuePosition(task.queue_position ?? null);
      setApprovalCallId(task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null);
      setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
    } catch (error) {
      showToast(error instanceof Error ? error.message : '任务审批失败');
    }
  }, [approvalCallId, currentTaskId, currentTaskStatus, showToast]);

  const handleSendWithSession = useCallback(async (message: string) => {
    if (!message.trim()) return;
    let id = currentSessionId;
    if (!id) { const session = await createSession(message.slice(0, 30)); id = session.id; setCurrentSessionId(id); }
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    try {
      const task = await createTask(id, message);
      setCurrentTaskId(task.id); setCurrentTaskStatus(task.status); setQueuePosition(task.queue_position ?? null); setApprovalCallId(null); setIsStreaming(true);
      startPolling(task.id, id);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '发送失败');
    }
  }, [currentSessionId, showToast, startPolling]);

  const handleSwitchSession = useCallback(async (id: string) => { const data = await getSession(id); setCurrentSessionId(id); setMessages(data.messages); }, []);
  const handleDeleteSession = useCallback(async (id: string) => { await deleteSession(id); if (id === currentSessionId) { setCurrentSessionId(''); setMessages([]); } await refreshSessions(); }, [currentSessionId, refreshSessions]);
  const handleNewChat = useCallback(() => { setCurrentSessionId(''); setMessages([]); setPendingApproval(null); setCurrentTaskId(null); setCurrentTaskStatus(null); setQueuePosition(null); setApprovalCallId(null); setIsStreaming(false); }, []);
  const handleStop = useCallback(async () => {
    if (!currentTaskId || !currentTaskStatus || TERMINAL_TASK_STATUSES.has(currentTaskStatus)) return;
    try {
      const task = await cancelTask(currentTaskId);
      setCurrentTaskStatus(task.status); setQueuePosition(task.queue_position ?? null); setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
    } catch (error) { showToast(error instanceof Error ? error.message : '停止任务失败'); }
  }, [currentTaskId, currentTaskStatus, showToast]);
  const handleCopy = useCallback((text: string) => { navigator.clipboard.writeText(text).then(() => showToast('已复制')); }, [showToast]);
  const handleRegenerate = useCallback(() => showToast('当前版本暂不支持重新生成'), [showToast]);
  const handleEditMessage = useCallback((_index: number, _content: string) => showToast('当前版本暂不支持编辑历史消息'), [showToast]);

  return { messages, isStreaming, streamingContent, toast, pendingApproval, currentSessionId, currentTaskId, currentTaskStatus, queuePosition, approvalCallId, sessions, handleSendWithSession, resolvePendingApproval, handleRegenerate, handleStop, handleNewChat, handleCopy, handleEditMessage, handleSwitchSession, handleDeleteSession };
}
