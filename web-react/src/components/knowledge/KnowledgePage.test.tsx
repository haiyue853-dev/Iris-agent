import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import KnowledgePage from './KnowledgePage';

const entry = {
  id: 'kb-000000000001',
  title: '多模态面试',
  category: '面经',
  source_url: null,
  source_type: 'manual',
  created_at: 1000,
  updated_at: 1000,
};

const hit = {
  entry_id: 'kb-000000000001',
  title: '多模态面试',
  content: '多模态大模型结构',
  source_url: null,
  score: 2,
};

describe('KnowledgePage', () => {
  it('lists knowledge and deletes one', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [entry] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    expect(await screen.findByText('多模态面试')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/knowledge/kb-000000000001'),
      { method: 'DELETE' },
    );
    expect(screen.queryByText('多模态面试')).not.toBeInTheDocument();
  });

  it('adds a knowledge entry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => entry });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText('标题'), '多模态面试');
    await user.type(screen.getByPlaceholderText('正文内容'), '多模态大模型结构');
    await user.click(screen.getByRole('button', { name: '添加到知识库' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('多模态面试')).toBeInTheDocument();
  });

  it('shows an empty state when there are no entries', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ entries: [] }) }));

    render(<KnowledgePage />);

    expect(await screen.findByText(/知识库还是空的/)).toBeInTheDocument();
  });

  it('searches the knowledge base', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ hits: [hit] }) });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText(/知识库中提问/), '多模态');
    await user.click(screen.getByRole('button', { name: '提问' }));
    expect(await screen.findByText('多模态大模型结构')).toBeInTheDocument();
  });
});
