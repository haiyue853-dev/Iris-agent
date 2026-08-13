import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AutomationPage from './AutomationPage';

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);

function reply(body: unknown) { return Promise.resolve({ ok: true, json: async () => body }); }

describe('AutomationPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/tasks/') && url.includes('/executions')) return reply({ executions: [{ id: 'run-1', task_id: 'task-1', trigger: 'manual', status: 'succeeded', summary: '新增 1 条热点', new_count: 1, failed_sources: [], item_ids: ['item-1'] }] });
      if (url.includes('/notifications')) return reply({ notifications: [{ id: 'notice-1', title: '热点雷达扫描', summary: '新增 1 条热点', task_id: 'task-1', item_ids: ['item-1'], read: false }] });
      if (url.includes('/automation/tasks')) return reply({ tasks: [{ id: 'task-1', name: '热点雷达扫描', schedule: '0 9 * * *', enabled: true }] });
      if (url.includes('/subscriptions')) return reply({ subscriptions: [{ id: 'sub-1', keyword: 'MCP' }] });
      return reply({ items: [{ id: 'item-1', title: 'MCP 协议更新', url: 'https://example.test/mcp', source: 'Tech', summary: '工具互操作性的新进展', keyword: 'MCP' }] });
    });
  });

  it('shows subscriptions and runs a configured routine', async () => {
    render(<AutomationPage />);
    expect((await screen.findAllByText('热点雷达扫描')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('MCP')).not.toHaveLength(0);
    expect(screen.getByRole('link', { name: 'MCP 协议更新' })).toHaveAttribute('href', 'https://example.test/mcp');
    expect(screen.getByText('1 条未读通知')).toBeInTheDocument();
    expect(screen.getByText('新增 1 条热点')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '标为已读' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/notifications/notice-1/read', { method: 'PUT' },
    ));

    fireEvent.click(screen.getByRole('button', { name: '立即运行' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/automation/tasks/task-1/run', { method: 'POST' },
    ));
  });
});
