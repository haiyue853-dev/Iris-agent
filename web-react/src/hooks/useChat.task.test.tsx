import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { cancelTask, createTask, getTask, resolveTaskApproval } from '../api/tasks';
import { getSession, streamChat } from '../api/chat';
import { useChat } from './useChat';

vi.mock('../api/chat', () => ({
  createSession: vi.fn(async () => ({ id: 'session-1' })),
  deleteSession: vi.fn(),
  getSession: vi.fn(),
  listSessions: vi.fn(async () => []),
  streamChat: vi.fn(),
  streamToolApproval: vi.fn(),
}));

vi.mock('../api/tasks', () => ({
  createTask: vi.fn(),
  getTask: vi.fn(),
  cancelTask: vi.fn(),
  resolveTaskApproval: vi.fn(),
}));

describe('useChat background task support', () => {
  it('keeps the submitted task id available for navigation', async () => {
    vi.mocked(createTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    const { result } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('hello'); });

    expect(result.current.currentTaskId).toBe('task-1');
    expect(streamChat).not.toHaveBeenCalled();
  });

  it('submits a background task, polls it, then refreshes the completed session', async () => {
    vi.useFakeTimers();
    vi.mocked(createTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    vi.mocked(getTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'completed', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] });
    vi.mocked(getSession).mockResolvedValue({ messages: [{ role: 'assistant', content: '完成回复' }] });
    const { result, unmount } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('开始'); });
    expect(createTask).toHaveBeenCalledWith('session-1', '开始');
    expect(streamChat).not.toHaveBeenCalled();
    expect(result.current.currentTaskId).toBe('task-1');
    expect(result.current.currentTaskStatus).toBe('queued');

    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(getTask).toHaveBeenCalledWith('task-1');
    expect(result.current.messages).toEqual([{ role: 'assistant', content: '完成回复' }]);
    expect(result.current.currentTaskStatus).toBe('completed');
    unmount();
    vi.useRealTimers();
  });

  it('approves the current awaiting task with its safe approval call id', async () => {
    vi.mocked(createTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    vi.mocked(getTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'awaiting_approval', approval_call_id: 'call-1', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] });
    vi.mocked(resolveTaskApproval).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'running', approval_call_id: null, session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:01Z' });
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('需要审批'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.approvalCallId).toBe('call-1');
    await act(async () => { await result.current.resolvePendingApproval('call-1', true); });

    expect(resolveTaskApproval).toHaveBeenCalledWith('task-1', 'call-1', true);
    expect(result.current.currentTaskStatus).toBe('running');
    unmount();
    vi.useRealTimers();
  });

  it('stops polling tasks left behind by session switching and creating a new chat', async () => {
    vi.useFakeTimers();
    vi.mocked(createTask)
      .mockResolvedValueOnce({ id: 'task-1', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' })
      .mockResolvedValueOnce({ id: 'task-2', request_summary: '后台任务', status: 'queued', session_id: 'session-2', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    vi.mocked(getTask).mockResolvedValue({ id: 'task-2', request_summary: '后台任务', status: 'running', session_id: 'session-2', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] });
    vi.mocked(getSession).mockResolvedValue({ messages: [] });
    const { result, unmount } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('第一个任务'); });
    await act(async () => { await result.current.handleSwitchSession('session-2'); });
    await act(async () => { await result.current.handleSendWithSession('第二个任务'); });
    vi.mocked(getTask).mockClear();
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(getTask).toHaveBeenCalledTimes(1);
    expect(getTask).toHaveBeenCalledWith('task-2');

    result.current.handleNewChat();
    vi.mocked(getTask).mockClear();
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(getTask).not.toHaveBeenCalled();
    unmount();
    vi.useRealTimers();
  });

  it('clears the previous session task state so the next session cannot stop it', async () => {
    vi.useFakeTimers();
    vi.mocked(createTask).mockResolvedValue({ id: 'task-a', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    vi.mocked(getTask).mockResolvedValue({ id: 'task-a', request_summary: '后台任务', status: 'running', queue_position: null, approval_call_id: null, session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] });
    vi.mocked(getSession).mockResolvedValue({ messages: [] });
    const { result, unmount } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('A 任务'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.currentTaskId).toBe('task-a');
    expect(result.current.currentTaskStatus).toBe('running');

    await act(async () => { await result.current.handleSwitchSession('session-2'); });
    expect(result.current.currentTaskId).toBeNull();
    expect(result.current.currentTaskStatus).toBeNull();
    expect(result.current.queuePosition).toBeNull();
    expect(result.current.approvalCallId).toBeNull();
    expect(result.current.isStreaming).toBe(false);
    await act(async () => { await result.current.handleStop(); });
    expect(cancelTask).not.toHaveBeenCalled();
    unmount();
    vi.useRealTimers();
  });

  it('submits each awaiting approval decision only once while the request is pending', async () => {
    vi.useFakeTimers();
    vi.mocked(createTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' });
    vi.mocked(getTask).mockResolvedValue({ id: 'task-1', request_summary: '后台任务', status: 'awaiting_approval', approval_call_id: 'call-1', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] });
    let resolveApproval!: (task: { id: string; request_summary: string; status: 'running'; session_id: string; created_at: string; updated_at: string }) => void;
    vi.mocked(resolveTaskApproval).mockImplementation(() => new Promise((resolve) => { resolveApproval = resolve; }));
    const { result, unmount } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('需要审批'); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    await act(async () => {
      void result.current.resolvePendingApproval('call-1', true);
      void result.current.resolvePendingApproval('call-1', true);
    });
    expect(resolveTaskApproval).toHaveBeenCalledTimes(1);
    expect(result.current.approvalSubmitting).toBe(true);
    await act(async () => { resolveApproval({ id: 'task-1', request_summary: '后台任务', status: 'running', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:01Z' }); });
    expect(result.current.approvalSubmitting).toBe(false);
    unmount();
    vi.useRealTimers();
  });

});
