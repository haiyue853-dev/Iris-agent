import { useCallback, useEffect, useRef, useState } from 'react';
import { createSession, deleteSession, getSession, listSessions } from '../api/chat';
import { cancelTask, createTask, getTask, resolveTaskApproval } from '../api/tasks';
import type { AgentEvent, Message, Session, TaskStatus } from '../types';

const TERMINAL_TASK_STATUSES = new Set<TaskStatus>(['completed', 'failed', 'stopped']);
type TaskPoller = {
  timer: number | null;
  sessionId: string;
  status: TaskStatus;
  queuePosition: number | null;
  approvalCallId: string | null;
};

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
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const currentSessionRef = useRef('');
  const currentTaskRef = useRef<string | null>(null);
  const pollersRef = useRef(new Map<string, TaskPoller>());
  const approvalRequestsRef = useRef(new Set<string>());
  const sessionSwitchRequestRef = useRef(0);

  const refreshSessions = useCallback(async () => setSessions(await listSessions()), []);
  useEffect(() => { refreshSessions().catch(() => undefined); }, [refreshSessions]);
  const showToast = useCallback((text: string) => { setToast(text); window.setTimeout(() => setToast(''), 1800); }, []);

  useEffect(() => { currentSessionRef.current = currentSessionId; }, [currentSessionId]);
  useEffect(() => { currentTaskRef.current = currentTaskId; }, [currentTaskId]);
  const clearPollers = useCallback((keepSessionId?: string) => {
    pollersRef.current.forEach((poller) => {
      if (keepSessionId === poller.sessionId) return;
      if (poller.timer !== null) window.clearInterval(poller.timer);
      poller.timer = null;
    });
  }, []);
  useEffect(() => () => { clearPollers(); pollersRef.current.clear(); }, [clearPollers]);

  const clearCurrentTaskState = useCallback(() => {
    currentTaskRef.current = null;
    setCurrentTaskId(null);
    setCurrentTaskStatus(null);
    setQueuePosition(null);
    setApprovalCallId(null);
    setApprovalSubmitting(false);
    setIsStreaming(false);
  }, []);

  const discardSessionTasks = useCallback((sessionId: string) => {
    pollersRef.current.forEach((poller, taskId) => {
      if (poller.sessionId !== sessionId) return;
      if (poller.timer !== null) window.clearInterval(poller.timer);
      pollersRef.current.delete(taskId);
    });
  }, []);

  const restoreSessionTask = useCallback((sessionId: string) => {
    const active = [...pollersRef.current.entries()].filter(([, poller]) => poller.sessionId === sessionId).at(-1);
    const taskId = active?.[0] ?? null;
    const poller = active?.[1];
    currentTaskRef.current = taskId ?? null;
    setCurrentTaskId(taskId ?? null);
    setCurrentTaskStatus(poller?.status ?? null);
    setQueuePosition(poller?.queuePosition ?? null);
    setApprovalCallId(poller?.approvalCallId ?? null);
    setApprovalSubmitting(false);
    setIsStreaming(poller ? !TERMINAL_TASK_STATUSES.has(poller.status) : false);
    return active;
  }, []);

  const pollTask = useCallback(async (taskId: string, sessionId: string) => {
    try {
      const task = await getTask(taskId);
      const poller = pollersRef.current.get(taskId);
      if (poller) {
        poller.status = task.status;
        poller.queuePosition = task.queue_position ?? null;
        poller.approvalCallId = task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null;
      }
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) {
        setCurrentTaskStatus(task.status);
        setQueuePosition(task.queue_position ?? null);
        setApprovalCallId(task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null);
        setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
      }
      if (!TERMINAL_TASK_STATUSES.has(task.status)) return;
      const finishedPoller = pollersRef.current.get(taskId);
      if (finishedPoller?.timer !== null && finishedPoller !== undefined) window.clearInterval(finishedPoller.timer);
      pollersRef.current.delete(taskId);
      if (task.status === 'completed' && currentSessionRef.current === sessionId) {
        const session = await getSession(sessionId);
        if (currentSessionRef.current === sessionId) setMessages(session.messages);
      }
      if (currentSessionRef.current === sessionId && task.status === 'failed') showToast('任务执行失败');
      if (currentSessionRef.current === sessionId && task.status === 'stopped') showToast('任务已停止');
      await refreshSessions();
    } catch (error) {
      showToast(error instanceof Error ? error.message : '任务状态查询失败');
    }
  }, [refreshSessions, showToast]);

  const startPolling = useCallback((taskId: string, sessionId: string) => {
    const existing = pollersRef.current.get(taskId);
    if (existing?.timer !== null && existing !== undefined) return;
    const timer = window.setInterval(() => { void pollTask(taskId, sessionId); }, 1000);
    if (existing) existing.timer = timer;
    else pollersRef.current.set(taskId, { timer, sessionId, status: 'queued', queuePosition: null, approvalCallId: null });
  }, [pollTask]);

  const resolvePendingApproval = useCallback(async (callId: string, approved: boolean) => {
    if (!currentTaskId || currentTaskStatus !== 'awaiting_approval' || approvalCallId !== callId) return;
    const taskId = currentTaskId;
    const sessionId = currentSessionId;
    const requestKey = `${taskId}:${callId}`;
    if (approvalRequestsRef.current.has(requestKey)) return;
    approvalRequestsRef.current.add(requestKey);
    setApprovalSubmitting(true);
    try {
      const task = await resolveTaskApproval(taskId, callId, approved);
      const poller = pollersRef.current.get(taskId);
      if (poller) {
        poller.status = task.status;
        poller.queuePosition = task.queue_position ?? null;
        poller.approvalCallId = task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null;
      }
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) {
        setCurrentTaskStatus(task.status);
        setQueuePosition(task.queue_position ?? null);
        setApprovalCallId(task.status === 'awaiting_approval' ? task.approval_call_id ?? null : null);
        setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
      }
    } catch (error) {
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) showToast(error instanceof Error ? error.message : '任务审批失败');
    } finally {
      approvalRequestsRef.current.delete(requestKey);
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) setApprovalSubmitting(false);
    }
  }, [approvalCallId, currentSessionId, currentTaskId, currentTaskStatus, showToast]);

  const handleSendWithSession = useCallback(async (message: string) => {
    if (!message.trim()) return;
    let id = currentSessionId;
    if (!id) { const session = await createSession(message.slice(0, 30)); id = session.id; setCurrentSessionId(id); }
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    try {
      const task = await createTask(id, message);
      currentTaskRef.current = task.id;
      setCurrentTaskId(task.id); setCurrentTaskStatus(task.status); setQueuePosition(task.queue_position ?? null); setApprovalCallId(null); setApprovalSubmitting(false); setIsStreaming(true);
      startPolling(task.id, id);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '发送失败');
    }
  }, [currentSessionId, showToast, startPolling]);

  const handleSwitchSession = useCallback(async (id: string) => {
    const requestId = ++sessionSwitchRequestRef.current;
    const data = await getSession(id);
    if (requestId !== sessionSwitchRequestRef.current) return;
    clearPollers(id);
    currentSessionRef.current = id;
    setCurrentSessionId(id);
    const active = restoreSessionTask(id);
    if (active) {
      const [taskId, poller] = active;
      startPolling(taskId, poller.sessionId);
      void pollTask(taskId, poller.sessionId);
    }
    setMessages(data.messages);
  }, [clearPollers, pollTask, restoreSessionTask, startPolling]);
  const handleDeleteSession = useCallback(async (id: string) => {
    await deleteSession(id);
    discardSessionTasks(id);
    if (id === currentSessionId) {
      sessionSwitchRequestRef.current += 1;
      currentSessionRef.current = '';
      setCurrentSessionId('');
      setMessages([]);
      setPendingApproval(null);
      clearCurrentTaskState();
    }
    await refreshSessions();
  }, [clearCurrentTaskState, currentSessionId, discardSessionTasks, refreshSessions]);
  const handleNewChat = useCallback(() => { clearPollers(); sessionSwitchRequestRef.current += 1; currentSessionRef.current = ''; setCurrentSessionId(''); setMessages([]); setPendingApproval(null); clearCurrentTaskState(); }, [clearCurrentTaskState, clearPollers]);
  const handleStop = useCallback(async () => {
    if (!currentTaskId || !currentTaskStatus || TERMINAL_TASK_STATUSES.has(currentTaskStatus)) return;
    const taskId = currentTaskId;
    const sessionId = currentSessionId;
    try {
      const task = await cancelTask(taskId);
      const poller = pollersRef.current.get(taskId);
      if (poller) {
        poller.status = task.status;
        poller.queuePosition = task.queue_position ?? null;
        poller.approvalCallId = null;
        if (TERMINAL_TASK_STATUSES.has(task.status)) {
          if (poller.timer !== null) window.clearInterval(poller.timer);
          pollersRef.current.delete(taskId);
        }
      }
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) {
        setCurrentTaskStatus(task.status);
        setQueuePosition(task.queue_position ?? null);
        setApprovalCallId(null);
        setApprovalSubmitting(false);
        setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
      }
    } catch (error) {
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) showToast(error instanceof Error ? error.message : '停止任务失败');
    }
  }, [currentSessionId, currentTaskId, currentTaskStatus, showToast]);
  const handleCopy = useCallback((text: string) => { navigator.clipboard.writeText(text).then(() => showToast('已复制')); }, [showToast]);
  const handleRegenerate = useCallback(() => showToast('当前版本暂不支持重新生成'), [showToast]);
  const handleEditMessage = useCallback((_index: number, _content: string) => showToast('当前版本暂不支持编辑历史消息'), [showToast]);

  return { messages, isStreaming, streamingContent, toast, pendingApproval, currentSessionId, currentTaskId, currentTaskStatus, queuePosition, approvalCallId, approvalSubmitting, sessions, handleSendWithSession, resolvePendingApproval, handleRegenerate, handleStop, handleNewChat, handleCopy, handleEditMessage, handleSwitchSession, handleDeleteSession };
}
