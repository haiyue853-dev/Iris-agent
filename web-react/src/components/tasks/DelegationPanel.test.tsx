import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import DelegationPanel from './DelegationPanel';


describe('DelegationPanel', () => {
  it('lists background delegations, opens details, and cancels active work', async () => {
    const record = {
      id: 'delegation-1', parent_task_id: 'task-1', status: 'running', goal: '分析代码',
      created_at: 1787587200, updated_at: 1787587260,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ delegations: [record] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...record, result: '', error: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...record, status: 'cancelled', result: '', error: 'cancelled' }) });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<DelegationPanel />);

    expect(await screen.findByText('分析代码')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /分析代码/ }));
    expect(await screen.findByText('父任务 task-1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '取消委派' }));

    await waitFor(() => expect(screen.getAllByText('cancelled').length).toBeGreaterThan(0));
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/delegations/delegation-1'),
      { method: 'DELETE' },
    );
  });
});
