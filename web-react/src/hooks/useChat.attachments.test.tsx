import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { getSession, streamChat, streamToolApproval } from '../api/chat';
import { deleteAttachment, uploadAttachment } from '../api/attachments';
import { useChat } from './useChat';

vi.mock('../api/chat', () => ({
  createSession: vi.fn(async () => ({ id: 'session-1' })),
  deleteSession: vi.fn(),
  getSession: vi.fn(),
  listSessions: vi.fn(async () => []),
  streamChat: vi.fn(async (_sessionId, _message, _signal, onEvent) => {
    onEvent({ type: 'task_started', data: { task_id: 'task-attachment-1' } });
    onEvent({ type: 'text_delta', data: { content: '已分析' } });
    onEvent({ type: 'tool_started', data: { call_id: 'call-1', name: 'read_attachment', arguments: {} } });
    onEvent({ type: 'tool_finished', data: { call_id: 'call-1', name: 'read_attachment', ok: true } });
    onEvent({ type: 'message_completed', data: { message_id: 'message-1' } });
  }),
  streamToolApproval: vi.fn(),
}));

vi.mock('../api/tasks', () => ({ createTask: vi.fn(), getTask: vi.fn(), cancelTask: vi.fn(), resolveTaskApproval: vi.fn() }));
vi.mock('../api/attachments', () => ({ uploadAttachment: vi.fn(), deleteAttachment: vi.fn() }));

describe('useChat attachments', () => {
  it('creates a new session before upload and sends only its ready attachment ids', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue({ id: 'attachment-1', original_name: 'notes.txt', media_type: 'text/plain', size_bytes: 4, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: [] });
    const { result } = renderHook(() => useChat());

    await act(async () => { await result.current.uploadFiles([new File(['memo'], 'notes.txt', { type: 'text/plain' })]); });
    expect(uploadAttachment).toHaveBeenCalledWith('session-1', expect.any(File));
    expect(result.current.attachments).toMatchObject([{ id: 'attachment-1', status: 'ready' }]);

    await act(async () => { await result.current.handleSendWithSession('请分析', ['attachment-1']); });
    expect(streamChat).toHaveBeenCalledWith('session-1', '请分析', expect.any(AbortSignal), expect.any(Function), ['attachment-1']);
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: '请分析', attachment_ids: ['attachment-1'] });
    expect(result.current.messages[1]).toMatchObject({ role: 'assistant', content: '已分析' });
  });

  it('keeps upload failures removable and does not send them', async () => {
    vi.mocked(uploadAttachment).mockRejectedValue(new Error('不支持该附件'));
    const { result } = renderHook(() => useChat());
    await act(async () => { await result.current.uploadFiles([new File(['bad'], 'bad.exe')]); });

    expect(result.current.attachments).toMatchObject([{ original_name: 'bad.exe', status: 'error', error: '不支持该附件' }]);
    await act(async () => { await result.current.removeAttachment(result.current.attachments[0].client_id); });
    expect(result.current.attachments).toEqual([]);
    expect(streamChat).not.toHaveBeenCalled();
  });

  it('keeps a ready chip when deletion fails so it can be retried', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue({ id: 'attachment-1', original_name: 'notes.txt', media_type: 'text/plain', size_bytes: 4, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: [] });
    vi.mocked(deleteAttachment).mockRejectedValue(new Error('删除失败，请重试'));
    const { result } = renderHook(() => useChat());
    await act(async () => { await result.current.uploadFiles([new File(['memo'], 'notes.txt', { type: 'text/plain' })]); });

    await act(async () => { await result.current.removeAttachment(result.current.attachments[0].client_id); });
    expect(result.current.attachments).toMatchObject([{ id: 'attachment-1', status: 'error', error: '删除失败，请重试' }]);
  });

  it('restores attachment metadata when switching to a historical session', async () => {
    vi.mocked(getSession).mockResolvedValue({ messages: [{ role: 'user', content: '请阅读', attachment_ids: ['attachment-1'], attachments: [{ id: 'attachment-1', original_name: 'notes.pdf', media_type: 'application/pdf', size_bytes: 8, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: ['第 1 页'] }] }] });
    const { result } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSwitchSession('session-history'); });
    expect(result.current.messages).toMatchObject([{ attachment_ids: ['attachment-1'], attachments: [{ original_name: 'notes.pdf', sources: ['第 1 页'] }] }]);
  });

  it('continues the attachment stream through the session tool approval endpoint', async () => {
    vi.mocked(streamChat).mockImplementationOnce(async (_sessionId, _message, _signal, onEvent) => {
      onEvent({ type: 'task_started', data: { task_id: 'task-approval' } });
      onEvent({ type: 'tool_approval_requested', data: { call_id: 'call-approval', name: 'read_attachment', arguments: {} } });
    });
    vi.mocked(streamToolApproval).mockImplementationOnce(async (_sessionId, _callId, _approved, _signal, onEvent) => {
      onEvent({ type: 'text_delta', data: { content: '审批后正文' } });
      onEvent({ type: 'message_completed', data: { message_id: 'message-after-approval' } });
    });
    const { result } = renderHook(() => useChat());
    await act(async () => { await result.current.uploadFiles([new File(['memo'], 'notes.txt', { type: 'text/plain' })]); });
    const sendPromise = result.current.handleSendWithSession('请读取', ['attachment-1']);
    await act(async () => { await sendPromise; });
    expect(result.current.approvalCallId).toBe('call-approval');

    await act(async () => { await result.current.resolvePendingApproval('call-approval', true); });
    expect(streamToolApproval).toHaveBeenCalledWith('session-1', 'call-approval', true, expect.any(AbortSignal), expect.any(Function));
    expect(result.current.messages.at(-1)).toMatchObject({ role: 'assistant', content: '审批后正文' });
  });
});
