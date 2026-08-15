import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import MemoryPage from './MemoryPage';

const entry = {
  id: 'memory-1',
  content: '用户偏好中文',
  category: 'preference',
  created_at: '2026-08-15T00:00:00Z',
  updated_at: '2026-08-15T00:00:00Z',
  source_session_id: null,
};

describe('MemoryPage', () => {
  it('lists memories and deletes one', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [entry] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<MemoryPage />);

    expect(await screen.findByText('用户偏好中文')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/memory/memory-1'),
      { method: 'DELETE' },
    );
    expect(screen.queryByText('用户偏好中文')).not.toBeInTheDocument();
  });

  it('adds a memory', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => entry });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<MemoryPage />);

    await user.type(screen.getByPlaceholderText('输入要记住的内容'), '用户偏好中文');
    await user.click(screen.getByRole('button', { name: '添加记忆' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('用户偏好中文')).toBeInTheDocument();
  });

  it('shows an empty state when there are no memories', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ entries: [] }) }));

    render(<MemoryPage />);

    expect(await screen.findByText('还没有任何记忆')).toBeInTheDocument();
  });
});
