import { describe, expect, it, vi } from 'vitest';

import { createTask, getTask, listTasks, resolveTaskApproval } from './tasks';

describe('task API', () => {
  it('loads safe task summaries and a selected task detail', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ tasks: [{ id: 'task-1', request_summary: 'Summarise the report', status: 'completed', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z' }] }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ id: 'task-1', request_summary: 'Summarise the report', status: 'completed', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z', events: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await expect(listTasks()).resolves.toHaveLength(1);
    await expect(getTask('task-1')).resolves.toMatchObject({ id: 'task-1' });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/api/tasks',
      'http://localhost:8000/api/tasks/task-1',
    ]);
  });

  it('submits a background task without opening a streaming response', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 202,
      json: async () => ({ id: 'task-queued', request_summary: '后台任务', status: 'queued', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(createTask('session-1', '整理项目状态')).resolves.toMatchObject({ id: 'task-queued', status: 'queued' });
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: 'session-1', message: '整理项目状态' }),
    });
  });

  it('resolves a task approval through the task queue route', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ id: 'task-1', status: 'running' }) });
    vi.stubGlobal('fetch', fetchMock);

    await resolveTaskApproval('task-1', 'call-1', false);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/tasks/task-1/tool-approvals/call-1', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: false }),
    });
  });
});
