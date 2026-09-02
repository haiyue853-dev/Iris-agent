import { useCallback, useEffect, useRef, useState } from 'react';
import { createSession, deleteSession, getSession, listSessions, streamChat, streamToolApproval } from '../api/chat';
import { deleteAttachment, uploadAttachment } from '../api/attachments';
import { cancelTask, createTask, getTask, resolveTaskApproval } from '../api/tasks';
import type { AgentEvent, Message, PendingAttachment, Session, TaskStatus } from '../types';

function toolActivityLabel(toolName: string): string {
  switch (toolName) {
    case 'web_search':
      return '正在联网搜索…';
    case 'fetch_page':
      return '正在抓取网页内容…';
    case 'add_knowledge':
    case 'search_knowledge':
      return '正在检索知识库…';
    case 'remember':
    case 'recall':
      return '正在检索历史对话…';
    case 'use_skill':
    case 'save_skill':
      return '正在调用技能…';
    case 'delegate_task':
    case 'delegate_tasks':
      return '正在委派子任务…';
    case 'read_file':
    case 'list_directory':
      return '正在读取文件…';
    case 'read_attachment':
      return '正在解析附件…';
    default:
      return toolName ? `正在调用 ${toolName}…` : '正在处理…';
  }
}

const TERMINAL_TASK_STATUSES = new Set<TaskStatus>(['completed', 'failed', 'stopped']);
type TaskPoller = {
  timer: number | null;
  sessionId: string;
  status: TaskStatus;
  queuePosition: number | null;
  approvalCallId: string | null;
};

type AttachmentStream = {
  sessionId: string;
  callId: string;
  signal: AbortSignal;
  onEvent: (event: AgentEvent) => void;
  complete: () => void;
};

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [toast, setToast] = useState('');
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<Extract<AgentEvent, { type: 'tool_approval_requested' }>['data'] | null>(null);
  const [currentTaskStatus, setCurrentTaskStatus] = useState<TaskStatus | null>(null);
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [approvalCallId, setApprovalCallId] = useState<string | null>(null);
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const [currentActivity, setCurrentActivity] = useState<string | null>(null);
  const activityResetTimerRef = useRef<number | null>(null);
  const currentSessionRef = useRef('');
  const currentTaskRef = useRef<string | null>(null);
  const pollersRef = useRef(new Map<string, TaskPoller>());
  const approvalRequestsRef = useRef(new Set<string>());
  const sessionSwitchRequestRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const attachmentStreamRef = useRef<AttachmentStream | null>(null);

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
  useEffect(() => () => {
    if (activityResetTimerRef.current !== null) {
      window.clearTimeout(activityResetTimerRef.current);
      activityResetTimerRef.current = null;
    }
  }, []);

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
    const attachmentStream = attachmentStreamRef.current;
    if (attachmentStream?.callId === callId && currentSessionRef.current === attachmentStream.sessionId) {
      setApprovalSubmitting(true);
      try {
        await streamToolApproval(attachmentStream.sessionId, callId, approved, attachmentStream.signal, attachmentStream.onEvent);
        setPendingApproval(null);
      } catch (error) {
        if ((error as Error).name !== 'AbortError') showToast(error instanceof Error ? error.message : '附件工具审批失败');
      } finally {
        if (attachmentStreamRef.current?.callId === callId) {
          attachmentStream.complete();
          attachmentStreamRef.current = null;
          streamAbortRef.current = null;
          setIsStreaming(false);
          setStreamingContent('');
          setApprovalSubmitting(false);
        }
      }
      return;
    }
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

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!files.length) return;
    let id = currentSessionRef.current || currentSessionId;
    if (!id) {
      const session = await createSession(files[0].name.slice(0, 30));
      id = session.id;
      currentSessionRef.current = id;
      setCurrentSessionId(id);
    }
    const pending = files.map((file) => ({ client_id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, original_name: file.name, status: 'uploading' as const }));
    setAttachments((prev) => [...prev, ...pending]);
    await Promise.all(files.map(async (file, index) => {
      const item = pending[index];
      try {
        const metadata = await uploadAttachment(id, file);
        setAttachments((prev) => prev.map((attachment) => attachment.client_id === item.client_id ? { ...metadata, client_id: item.client_id, status: 'ready' as const } : attachment));
      } catch (error) {
        setAttachments((prev) => prev.map((attachment) => attachment.client_id === item.client_id ? { ...item, status: 'error' as const, error: error instanceof Error ? error.message : '上传失败' } : attachment));
      }
    }));
  }, [currentSessionId]);

  const removeAttachment = useCallback(async (clientId: string) => {
    const item = attachments.find((attachment) => attachment.client_id === clientId);
    if (item?.id && (currentSessionRef.current || currentSessionId)) {
      try {
        await deleteAttachment(currentSessionRef.current || currentSessionId, item.id);
      } catch (error) {
        setAttachments((prev) => prev.map((attachment) => attachment.client_id === clientId
          ? { ...attachment, status: 'error', error: error instanceof Error ? error.message : '删除失败，请重试' }
          : attachment));
        showToast(error instanceof Error ? error.message : '删除失败，请重试');
        return;
      }
    }
    setAttachments((prev) => prev.filter((attachment) => attachment.client_id !== clientId));
  }, [attachments, currentSessionId, showToast]);

  const handleSendWithSession = useCallback(async (message: string, attachmentIds: string[] = []) => {
    const selectedIds = attachmentIds.filter(Boolean);
    if (!message.trim() && !selectedIds.length) return;
    let id = currentSessionId;
    if (!id) { const session = await createSession(message.slice(0, 30) || '附件会话'); id = session.id; currentSessionRef.current = id; setCurrentSessionId(id); }
    const selectedAttachments = attachments
      .filter((attachment) => selectedIds.includes(attachment.id ?? '') && attachment.status === 'ready' && Boolean(attachment.id))
      .map((attachment) => ({
        id: attachment.id as string,
        original_name: attachment.original_name,
        media_type: attachment.media_type ?? 'application/octet-stream',
        size_bytes: attachment.size_bytes ?? 0,
        created_at: attachment.created_at ?? '',
        extraction_status: attachment.extraction_status ?? 'pending',
        extraction_message: attachment.extraction_message,
        text_truncated: attachment.text_truncated ?? false,
        sources: attachment.sources ?? [],
      }));
    setMessages(prev => [...prev, { role: 'user', content: message, attachment_ids: selectedIds, attachments: selectedAttachments }]);
    setAttachments((prev) => prev.filter((attachment) => !selectedIds.includes(attachment.id ?? '')));
    if (selectedIds.length) {
      const controller = new AbortController();
      let streamedContent = '';
      let finalContent = '';
      streamAbortRef.current = controller;
      setStreamingContent('');
      setIsStreaming(true);
      try {
        const onEvent = (event: AgentEvent) => {
          if (event.type === 'task_started') {
            currentTaskRef.current = event.data.task_id;
            setCurrentTaskId(event.data.task_id);
            setCurrentTaskStatus('running');
            setQueuePosition(null);
            setApprovalCallId(null);
            return;
          }
          if (event.type === 'text_delta') {
            streamedContent += event.data.content;
            setStreamingContent(streamedContent);
            setCurrentActivity('正在生成回复…');
            if (activityResetTimerRef.current !== null) {
              window.clearTimeout(activityResetTimerRef.current);
              activityResetTimerRef.current = null;
            }
            return;
          }
          if (event.type === 'tool_started' || event.type === 'tool_finished') {
            setCurrentTaskStatus('running');
            if (event.type === 'tool_started') {
              const toolName = String(event.data.name || '');
              setCurrentActivity(toolActivityLabel(toolName));
            } else {
              setCurrentActivity('正在分析工具结果…');
            }
            if (activityResetTimerRef.current !== null) {
              window.clearTimeout(activityResetTimerRef.current);
            }
            activityResetTimerRef.current = window.setTimeout(() => {
              setCurrentActivity(null);
              activityResetTimerRef.current = null;
            }, 15000);
            return;
          }
          if (event.type === 'tool_approval_requested') {
            attachmentStreamRef.current = { sessionId: id, callId: event.data.call_id, signal: controller.signal, onEvent, complete };
            if (!currentTaskRef.current) setPendingApproval(event.data);
            setCurrentTaskStatus('awaiting_approval');
            setApprovalCallId(event.data.call_id);
            return;
          }
          if (event.type === 'paused') {
            setCurrentTaskStatus('awaiting_approval');
            if (event.data.call_id) setApprovalCallId(event.data.call_id);
            return;
          }
          if (event.type === 'error') {
            setCurrentTaskStatus('failed');
            showToast(event.data.message);
            return;
          }
          if (event.type === 'message_completed' && event.data.content?.trim()) {
            finalContent = event.data.content;
            setStreamingContent(finalContent);
          }
          if (event.type === 'message_completed') {
            setCurrentTaskStatus('completed');
            setCurrentActivity(null);
            if (activityResetTimerRef.current !== null) {
              window.clearTimeout(activityResetTimerRef.current);
              activityResetTimerRef.current = null;
            }
          }
        };
        const complete = () => {
          const completedContent = finalContent || streamedContent;
          if (completedContent) setMessages((prev) => [...prev, { role: 'assistant', content: completedContent, attachments: selectedAttachments }]);
        };
        attachmentStreamRef.current = { sessionId: id, callId: '', signal: controller.signal, onEvent, complete };
        await streamChat(id, message, controller.signal, onEvent, selectedIds);
        if (attachmentStreamRef.current?.sessionId === id && attachmentStreamRef.current.callId) return;
        complete();
      } catch (error) {
        if ((error as Error).name !== 'AbortError') showToast(error instanceof Error ? error.message : '发送失败');
      } finally {
        if (!attachmentStreamRef.current || attachmentStreamRef.current.sessionId !== id || !attachmentStreamRef.current.callId) {
          streamAbortRef.current = null;
          attachmentStreamRef.current = null;
          setIsStreaming(false);
          setStreamingContent('');
        }
      }
      return;
    }
    try {
      const task = await createTask(id, message);
      currentTaskRef.current = task.id;
      setCurrentTaskId(task.id); setCurrentTaskStatus(task.status); setQueuePosition(task.queue_position ?? null); setApprovalCallId(null); setApprovalSubmitting(false); setIsStreaming(true);
      startPolling(task.id, id);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '发送失败');
    }
  }, [attachments, currentSessionId, showToast, startPolling]);

  const handleSwitchSession = useCallback(async (id: string) => {
    const requestId = ++sessionSwitchRequestRef.current;
    const data = await getSession(id);
    if (requestId !== sessionSwitchRequestRef.current) return;
    clearPollers(id);
    currentSessionRef.current = id;
    setCurrentSessionId(id);
    setAttachments([]);
    const active = restoreSessionTask(id);
    if (active) {
      const [taskId, poller] = active;
      startPolling(taskId, poller.sessionId);
      void pollTask(taskId, poller.sessionId);
    }
    setMessages(data.messages);
  }, [clearPollers, pollTask, restoreSessionTask, startPolling]);
  const handleRefreshSession = useCallback(async (id: string) => {
    const data = await getSession(id);
    if (currentSessionRef.current === id) {
      setMessages(data.messages);
      return data.messages;
    }
    return null;
  }, []);
  const handleDeleteSession = useCallback(async (id: string) => {
    await deleteSession(id);
    discardSessionTasks(id);
    if (id === currentSessionId) {
      sessionSwitchRequestRef.current += 1;
      currentSessionRef.current = '';
      setCurrentSessionId('');
      setMessages([]);
      setAttachments([]);
      setPendingApproval(null);
      clearCurrentTaskState();
    }
    await refreshSessions();
  }, [clearCurrentTaskState, currentSessionId, discardSessionTasks, refreshSessions]);
  const handleNewChat = useCallback(() => { clearPollers(); sessionSwitchRequestRef.current += 1; currentSessionRef.current = ''; setCurrentSessionId(''); setMessages([]); setAttachments([]); setPendingApproval(null); clearCurrentTaskState(); }, [clearCurrentTaskState, clearPollers]);
  const handleStop = useCallback(async () => {
    // 1) 立刻清掉所有"还在跑"的 UI 信号——不等 abort 传播完成。
    //    否则用户点完"停止"还会看见转圈和"正在分析…"几百毫秒。
    if (activityResetTimerRef.current !== null) {
      window.clearTimeout(activityResetTimerRef.current);
      activityResetTimerRef.current = null;
    }
    const hadActiveStream = streamAbortRef.current !== null;
    setIsStreaming(false);
    setStreamingContent('');
    setCurrentActivity(null);
    setApprovalCallId(null);
    setApprovalSubmitting(false);

    // 2) 立即停掉当前会话任务的轮询器，避免后续 tick 又把 status 覆盖回 running。
    if (currentTaskId) {
      const poller = pollersRef.current.get(currentTaskId);
      if (poller) {
        if (poller.timer !== null) window.clearInterval(poller.timer);
        poller.timer = null;
        poller.status = 'stopped';
        pollersRef.current.delete(currentTaskId);
      }
    }
    setCurrentTaskStatus('stopped');
    setQueuePosition(null);

    // 3) 关流。流式路径下，AbortController 一旦 abort 就会驱动 runtime 立即停止 yield。
    if (hadActiveStream) {
      streamAbortRef.current?.abort();
      streamAbortRef.current = null;
      return;
    }

    // 4) 队列/任务路径：后台 cancelTask 异步执行，UI 已经先一步反映"已停止"。
    if (!currentTaskId || !currentTaskStatus || TERMINAL_TASK_STATUSES.has(currentTaskStatus)) return;
    const taskId = currentTaskId;
    const sessionId = currentSessionId;
    try {
      const task = await cancelTask(taskId);
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) {
        setCurrentTaskStatus(task.status);
        setQueuePosition(task.queue_position ?? null);
        setIsStreaming(!TERMINAL_TASK_STATUSES.has(task.status));
      }
    } catch (error) {
      if (currentTaskRef.current === taskId && currentSessionRef.current === sessionId) showToast(error instanceof Error ? error.message : '停止任务失败');
    }
  }, [currentSessionId, currentTaskId, currentTaskStatus, showToast]);
  const handleCopy = useCallback((text: string) => { navigator.clipboard.writeText(text).then(() => showToast('已复制')); }, [showToast]);
  const handleRegenerate = useCallback(() => showToast('当前版本暂不支持重新生成'), [showToast]);
  const handleEditMessage = useCallback((_index: number, _content: string) => showToast('当前版本暂不支持编辑历史消息'), [showToast]);

  return { messages, isStreaming, streamingContent, currentActivity, toast, pendingApproval, currentSessionId, currentTaskId, currentTaskStatus, queuePosition, approvalCallId, approvalSubmitting, sessions, attachments, uploadFiles, removeAttachment, handleSendWithSession, resolvePendingApproval, handleRegenerate, handleStop, handleNewChat, handleCopy, handleEditMessage, handleSwitchSession, handleRefreshSession, handleDeleteSession };
}
