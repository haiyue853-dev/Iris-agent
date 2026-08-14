import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import TaskCenterPage from './TaskCenterPage';

const task = { id: 'task-1', request_summary: '整理项目状态', status: 'awaiting_approval', session_id: 'session-1', created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:01:00Z' };
const detail = { ...task, events: [{ id: 'event-1', type: 'approval_requested', label: '等待工具审批：write_file', tool_name: 'write_file', created_at: '2026-08-13T12:00:10Z', secret: 'must never render' }], tool_arguments: { token: 'must never render' } };

describe('TaskCenterPage', () => {
  it('renders a task summary and only safe timeline fields', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [task] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => detail }));

    render(<TaskCenterPage />);

    expect((await screen.findAllByText('整理项目状态')).length).toBeGreaterThan(0);
    expect(await screen.findByText('等待工具审批：write_file')).toBeInTheDocument();
    expect(screen.getAllByText('awaiting_approval').length).toBeGreaterThan(0);
    expect(screen.queryByText('must never render')).not.toBeInTheDocument();
  });

  it('shows a safe error and retries loading', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: { message: 'internal secret' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [task] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => detail });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<TaskCenterPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('无法加载任务中心');
    expect(screen.queryByText('internal secret')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试' }));
    await waitFor(() => expect(screen.getAllByText('整理项目状态').length).toBeGreaterThan(0));
  });

  it('keeps the task list visible when detail loading fails and retries only the detail', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [task] }) })
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: { message: 'sensitive failure' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => detail });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<TaskCenterPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('无法加载任务详情');
    expect(screen.getAllByText('整理项目状态').length).toBeGreaterThan(0);
    expect(screen.queryByText('sensitive failure')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试详情' }));
    expect(await screen.findByText('等待工具审批：write_file')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('keeps the newest selected task detail when earlier requests finish late', async () => {
    let resolveEarlier!: (value: unknown) => void;
    let resolveLatest!: (value: unknown) => void;
    const earlier = new Promise((resolve) => { resolveEarlier = resolve; });
    const latest = new Promise((resolve) => { resolveLatest = resolve; });
    const second = { ...detail, id: 'task-2', request_summary: '第二个任务' };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [task, { ...task, id: 'task-2', request_summary: '第二个任务' }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => detail })
      .mockImplementationOnce(() => earlier)
      .mockImplementationOnce(() => latest);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<TaskCenterPage />);
    await screen.findByText('等待工具审批：write_file');
    await user.click(screen.getByRole('button', { name: /整理项目状态/ }));
    await user.click(screen.getByRole('button', { name: /第二个任务/ }));
    expect(screen.getByText('正在加载详情…')).toBeInTheDocument();
    resolveEarlier({ ok: true, json: async () => detail });
    await waitFor(() => expect(screen.getByText('正在加载详情…')).toBeInTheDocument());
    resolveLatest({ ok: true, json: async () => second });
    expect(await screen.findByRole('heading', { name: '第二个任务' })).toBeInTheDocument();
  });
});
