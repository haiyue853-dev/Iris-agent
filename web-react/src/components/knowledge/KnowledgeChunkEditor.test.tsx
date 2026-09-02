import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { KnowledgeChunkEditor } from './KnowledgeChunkEditor';

const chunk = { id: 'chunk-1', content: '原始切片内容', location: '第 2 页' };

describe('KnowledgeChunkEditor', () => {
  it('edits one chunk without changing its id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ chunk: { ...chunk, content: '修正后的内容', location: '人工修订' }, revisions: [], embedding_updated: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const onUpdated = vi.fn();
    const user = userEvent.setup();
    render(<KnowledgeChunkEditor documentId="doc-1" chunk={chunk} index={0} active={false} onUpdated={onUpdated} />);

    await user.click(screen.getByRole('button', { name: '编辑切片 1' }));
    await user.clear(screen.getByLabelText('切片内容 1'));
    await user.type(screen.getByLabelText('切片内容 1'), '修正后的内容');
    await user.clear(screen.getByLabelText('切片位置 1'));
    await user.type(screen.getByLabelText('切片位置 1'), '人工修订');
    await user.click(screen.getByRole('button', { name: '保存切片 1' }));

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/doc-1/chunks/chunk-1', expect.objectContaining({ method: 'PATCH' }));
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ id: 'chunk-1', content: '修正后的内容' }));
  });

  it('shows and restores an earlier chunk revision', async () => {
    const revision = { id: 'revision-1', chunk_id: 'chunk-1', content: '旧版本内容', location: '第 1 页', created_at: 1000 };
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => ({ ok: true, json: async () => init?.method === 'POST' ? { chunk: { ...chunk, content: revision.content, location: revision.location }, revisions: [], embedding_updated: true } : { revisions: [revision] } }));
    vi.stubGlobal('fetch', fetchMock);
    const onUpdated = vi.fn();
    const user = userEvent.setup();
    render(<KnowledgeChunkEditor documentId="doc-1" chunk={chunk} index={0} active={false} onUpdated={onUpdated} />);

    await user.click(screen.getByRole('button', { name: '查看切片 1 历史' }));
    expect(await screen.findByText('旧版本内容')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '恢复切片 1 的此版本' }));

    expect(fetchMock).toHaveBeenLastCalledWith('http://localhost:8000/api/knowledge/doc-1/chunks/chunk-1/revisions/revision-1/restore', { method: 'POST' });
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ id: 'chunk-1', content: '旧版本内容' }));
  });
});
