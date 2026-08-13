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
      if (url.includes('/tasks/') && url.includes('/executions')) return reply({ executions: [] });
      if (url.includes('/automation/tasks')) return reply({ tasks: [{ id: 'task-1', name: '热点雷达扫描', schedule: '0 9 * * *', enabled: true }] });
      if (url.includes('/subscriptions')) return reply({ subscriptions: [{ id: 'sub-1', keyword: 'MCP' }] });
      return reply({ items: [] });
    });
  });

  it('shows subscriptions and runs a configured routine', async () => {
    render(<AutomationPage />);
    expect(await screen.findByText('热点雷达扫描')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '立即运行' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/automation/tasks/task-1/run', { method: 'POST' },
    ));
  });
});
