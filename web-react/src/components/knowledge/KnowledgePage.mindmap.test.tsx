import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import KnowledgePage from './KnowledgePage';

afterEach(() => vi.unstubAllGlobals());

describe('KnowledgePage document mind map', () => {
  it('opens a document in mind-map view and keeps relations as a separate tab', async () => {
    const entry = { id: 'doc-1', title: 'Iris 知识库', category: '文档', source_url: null, source_type: 'manual', created_at: 1, updated_at: 1, status: 'ready' };
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      let body: unknown = {};
      if (url.endsWith('/api/knowledge/collections')) body = { collections: [] };
      else if (url.includes('/api/knowledge/topics')) body = { topics: [] };
      else if (url.includes('/api/knowledge/stats')) body = { documents: 1, ready: 1, indexing: 0, failed: 0, chunks: 1, nodes: 0, edges: 0 };
      else if (url.includes('/api/knowledge/graph')) body = { nodes: [], edges: [] };
      else if (url.endsWith('/api/knowledge/doc-1/mindmap')) body = { document_id: 'doc-1', title: entry.title, nodes: [{ id: 'root', parent_id: null, label: entry.title, summary: '全文总结', kind: 'root', ordinal: 0, evidence_chunk_ids: [] }, { id: 'branch-1', parent_id: 'root', label: '核心主题', summary: '主题总结', kind: 'branch', ordinal: 0, evidence_chunk_ids: ['chunk-1'] }] };
      else if (url.endsWith('/api/knowledge/doc-1')) body = { ...entry, content: '全文', chunks: [{ id: 'chunk-1', content: '主题原文', location: null }] };
      else if (url.includes('/api/knowledge?')) body = { documents: [entry] };
      return { ok: true, json: async () => body } as Response;
    }));

    render(<KnowledgePage />);
    fireEvent.click(await screen.findByText('Iris 知识库'));

    expect(await screen.findByRole('tree', { name: '文档思维导图' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '文档思维导图' })).toHaveClass('active');
    fireEvent.click(screen.getByRole('button', { name: '跨资料关系图' }));
    await waitFor(() => expect(screen.getByLabelText('知识图谱')).toBeInTheDocument());
  });
});
