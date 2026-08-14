import { describe, expect, it, vi } from 'vitest';

import { getTask, listTasks } from './tasks';

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
});
