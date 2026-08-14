import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { streamChat } from '../api/chat';
import { useChat } from './useChat';

vi.mock('../api/chat', () => ({
  createSession: vi.fn(async () => ({ id: 'session-1' })),
  deleteSession: vi.fn(),
  getSession: vi.fn(),
  listSessions: vi.fn(async () => []),
  streamChat: vi.fn(),
  streamToolApproval: vi.fn(),
}));

describe('useChat task stream support', () => {
  it('keeps the task id emitted by the chat stream available for navigation', async () => {
    vi.mocked(streamChat).mockImplementation(async (_sessionId, _message, _signal, onEvent) => {
      onEvent({ type: 'task_started', data: { task_id: 'task-1' } });
    });
    const { result } = renderHook(() => useChat());

    await act(async () => { await result.current.handleSendWithSession('hello'); });

    expect(result.current.currentTaskId).toBe('task-1');
  });

});
