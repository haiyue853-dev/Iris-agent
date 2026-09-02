import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { RetrievalDebugger } from './RetrievalDebugger';

const candidate = { rank: 1, document_id: 'doc-1', chunk_id: 'chunk-1', title: 'RAG 基础', content: '关键词与向量组成混合召回。', location: '第 2 页', score: 0.8, keyword_score: 0.1, vector_score: 0.2, graph_score: 0, reranker_score: 0.9, routes: ['keyword', 'vector', 'reranker'] };

describe('RetrievalDebugger', () => {
  it('shows stage ranks, top-k hits and records a failed case', async () => {
    const trace = { query: '混合召回', retrieval_query: '混合召回', collection_id: 'collection-team', candidate_limit: 30, elapsed_ms: 18, config: { top_k: 5, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 }, stages: [
      { key: 'keyword', label: '关键词召回', enabled: true, elapsed_ms: 12, candidates: [candidate] },
      { key: 'final', label: 'MMR 最终结果', enabled: true, elapsed_ms: 1, candidates: [candidate] },
    ], hits: [candidate] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => trace });
    vi.stubGlobal('fetch', fetchMock);
    const openSource = vi.fn();
    const user = userEvent.setup();
    render(<RetrievalDebugger collectionId="collection-team" onOpenSource={openSource} />);

    await user.type(screen.getByLabelText('调试问题'), '混合召回');
    await user.click(screen.getByRole('button', { name: '运行检索调试' }));

    expect(await screen.findByText('关键词召回')).toBeInTheDocument();
    expect(screen.getByText('总耗时 18 ms')).toBeInTheDocument();
    expect(screen.getByText('1 条 · 12 ms')).toBeInTheDocument();
    expect(screen.getByText('MMR 最终结果')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '标记 chunk-1 为正确切片（关键词召回）' }));
    expect(screen.getByText('Top 1 命中')).toBeInTheDocument();
    expect(screen.getByText('Top 3 命中')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '打开切片 chunk-1（MMR 最终结果）' }));
    expect(openSource).toHaveBeenCalledWith('doc-1', 'chunk-1');
    await user.click(screen.getByRole('button', { name: '加入 Bad Case' }));
    expect(fetchMock).toHaveBeenLastCalledWith('http://localhost:8000/api/knowledge/bad-cases', expect.objectContaining({ method: 'POST' }));
  });
});
