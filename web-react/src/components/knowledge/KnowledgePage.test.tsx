import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { KnowledgeEntry, KnowledgeSearchHit } from '../../types';
import KnowledgePage from './KnowledgePage';

const entry: KnowledgeEntry = {
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

function mockKnowledgeApi(entries: KnowledgeEntry[] = [], hits: KnowledgeSearchHit[] = [], collections: Array<{ id: string; name: string }> = [], chunks: Array<{ id: string; content: string; location?: string }> = [], evaluationHistory: Array<{ id: string; created_at: number; total: number; hit_count: number; judged_total: number; recall_at_1: number | null; recall_at_3: number | null; mrr: number | null; config: { top_k: number; candidate_multiplier: number; minimum_relevance_score: number; mmr_relevance_weight: number } }> = [], evaluation?: object, badCases: Array<{ id: string; question: string; collection_id: string; expected_title?: string; expected_answer?: string; reason?: string }> = []) {
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    let body: unknown = { entries };
    if (url.includes('/api/knowledge/evaluate/history')) body = { items: evaluationHistory };
    else if (url.includes('/api/knowledge/evaluate/validate')) body = { summary: { total: 2, annotated: 1, duplicates: 0, empty_annotations: 1, invalid_chunks: 1 }, rows: [{ index: 0, duplicate: false, empty_annotation: false, invalid_chunk_ids: ['chunk-stale'] }, { index: 1, duplicate: false, empty_annotation: true, invalid_chunk_ids: [] }] };
    else if (url.includes('/api/knowledge/evaluate/gate')) body = { thresholds: { recall_at_1: 0.7, recall_at_3: 0.8, mrr: 0.75 } };
    else if (url.includes('/api/knowledge/bad-cases')) body = init?.method === 'POST' ? { id: 'bad-created', question: '发布计划在哪里', collection_id: 'collection-general' } : { cases: badCases };
    else if (url.endsWith('/api/knowledge/evaluate')) body = evaluation || { total: 0, hit_count: 0, judged_total: 0, route_coverage: {}, recommendations: [], results: [] };
    else if (url.includes('/api/knowledge/search/debug')) body = { query: '混合召回', collection_id: 'collection-general', candidate_limit: 30, config: { top_k: 5, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 }, stages: [], hits: [] };
    else if (url.includes('/api/knowledge/search')) body = { hits };
    else if (url.includes('/api/knowledge/runtime')) body = { config: { embedding_enabled: true, embedding_model: 'bge-m3', embedding_base_url: 'http://localhost:11434', semantic_split_enabled: true, semantic_split_model: 'bge-m3', semantic_split_base_url: 'http://localhost:11434', graph_enabled: true, graph_model: 'deepseek-r1:8b', graph_base_url: 'http://localhost:11434', image_enabled: false, image_model: 'qwen2.5vl:7b', image_base_url: 'http://localhost:11434', reranker_enabled: true, reranker_provider: 'ollama', reranker_model: 'deepseek-r1:8b', reranker_base_url: 'http://localhost:11434', mmr_relevance_weight: 0.7 }, components: [{ key: 'embedding', label: '向量模型', enabled: true, provider: 'ollama', model: 'bge-m3', base_url: 'http://localhost:11434', status: 'untested', message: '尚未测试', latency_ms: null }] };
    else if (url.includes('/retrieval-config')) body = { config: { top_k: 5, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 } };
    else if (url.includes('/api/knowledge/index-progress')) body = { items: entries.map((item) => ({ document_id: item.id, stage: 'embedding', message: '正在生成向量索引', updated_at: 1000 })) };
    else if (url.includes('/mindmap')) body = { nodes: [] };
    else if (url.includes('/chunks/') && init?.method === 'PATCH') {
      const request = JSON.parse(String(init.body || '{}'));
      const chunkId = url.split('/chunks/')[1].split('/')[0];
      body = { chunk: { id: chunkId, document_id: entries[0]?.id, content: request.content, location: request.location }, revisions: [], embedding_updated: true };
    }
    else if (url.includes('/chunks/') && url.includes('/revisions')) body = { revisions: [] };
    else if (/\/api\/knowledge\/kb-/.test(url) && !url.includes('/mindmap')) body = { ...entries[0], content: '多模态大模型结构', chunks };
    else if (url.includes('/api/knowledge/collections')) body = { collections };
    else if (url.includes('/api/knowledge/topics')) body = { topics: [] };
    else if (url.includes('/api/knowledge/stats')) body = { documents: entries.length, ready: entries.length, indexing: 0, failed: 0, chunks: 0, nodes: 0, edges: 0 };
    else if (url.includes('/api/knowledge/graph')) body = { nodes: [], edges: [] };
    else if (init?.method === 'POST') body = entry;
    else if (init?.method === 'DELETE') body = { ok: true };
    return { ok: true, json: async () => body };
  });
}

describe('KnowledgePage', () => {
  it('includes the staged retrieval debugger', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry], [], [{ id: 'collection-general', name: '默认知识库' }]));

    render(<KnowledgePage />);

    expect(await screen.findByText('检索调试台')).toBeInTheDocument();
  });

  it('lists knowledge and deletes one', async () => {
    const fetchMock = mockKnowledgeApi([entry]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    expect(await screen.findByText('多模态面试')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: '删除' }).find((button) => !button.hasAttribute('disabled'))!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/knowledge/kb-000000000001'),
      expect.objectContaining({ method: 'DELETE' }),
    ));
    expect(screen.queryByText('多模态面试')).not.toBeInTheDocument();
  });

  it('adds a knowledge entry', async () => {
    const fetchMock = mockKnowledgeApi();
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText('标题'), '多模态面试');
    await user.type(screen.getByPlaceholderText('正文内容'), '多模态大模型结构');
    await user.click(screen.getByRole('button', { name: '保存资料' }));
    expect(await screen.findByText('多模态面试')).toBeInTheDocument();
  });

  it('offers delete action in the opened document detail', async () => {
    const fetchMock = mockKnowledgeApi([entry]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    const row = (await screen.findByText('多模态面试')).closest('li');
    if (!(row instanceof HTMLElement)) throw new Error('Expected knowledge row');
    await user.click(within(row).getByRole('button', { name: /多模态面试/ }));
    await screen.findByText('多模态大模型结构');
    await user.click(screen.getByRole('button', { name: '删除资料' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/knowledge/kb-000000000001'),
      expect.objectContaining({ method: 'DELETE' }),
    ));
  });

  it('restores document detail after the panel is closed', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry]));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    const row = (await screen.findByText('多模态面试')).closest('li');
    if (!(row instanceof HTMLElement)) throw new Error('Expected knowledge row');
    await user.click(within(row).getByRole('button', { name: /多模态面试/ }));
    await user.click(await screen.findByRole('button', { name: '关闭' }));

    expect(screen.queryByRole('button', { name: '关闭' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '打开资料详情' }));

    expect(await screen.findByRole('button', { name: '关闭' })).toBeInTheDocument();
  });

  it('focuses the source chunk requested by a chat citation', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry], [], [], [
      { id: 'chunk-7', location: '第 3 节', content: '这是被回答引用的原文段落。' },
    ]));

    render(<KnowledgePage openDocumentId={entry.id} openChunkId="chunk-7" />);

    const source = await screen.findByText('这是被回答引用的原文段落。');
    expect(source.closest('[data-citation-target]')).toHaveAttribute('data-citation-target', 'true');
    expect(screen.getByText('第 3 节')).toBeInTheDocument();
  });

  it('edits an individual source chunk from document detail', async () => {
    const fetchMock = mockKnowledgeApi([entry], [], [], [{ id: 'chunk-7', location: '第 3 节', content: '需要清理的过程提示。' }]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<KnowledgePage openDocumentId={entry.id} openChunkId="chunk-7" />);

    await user.click(await screen.findByRole('button', { name: '编辑切片 1' }));
    await user.clear(screen.getByLabelText('切片内容 1'));
    await user.type(screen.getByLabelText('切片内容 1'), '清理后的有效知识。');
    await user.click(screen.getByRole('button', { name: '保存切片 1' }));

    expect(await screen.findByText('清理后的有效知识。')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/kb-000000000001/chunks/chunk-7', expect.objectContaining({ method: 'PATCH' }));
  });

  it('shows an inline preview for a previewable uploaded source file', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([{ ...entry, source_type: 'upload', media_type: 'application/pdf', original_name: 'source.pdf' }], [], [], []));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    const row = (await screen.findByText('多模态面试')).closest('li');
    if (!(row instanceof HTMLElement)) throw new Error('Expected knowledge row');
    await user.click(within(row).getByRole('button', { name: /多模态面试/ }));

    expect(await screen.findByTitle('原文件预览：多模态面试')).toHaveAttribute('src', 'http://localhost:8000/api/knowledge/kb-000000000001/source');
  });

  it('opens a PDF preview on the page of the cited chunk', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([
      { ...entry, source_type: 'upload', media_type: 'application/pdf', original_name: 'source.pdf' },
    ], [], [], [
      { id: 'chunk-page-3', location: '第 3 页', content: '第三页被引用的原文。' },
    ]));

    render(<KnowledgePage openDocumentId={entry.id} openChunkId="chunk-page-3" />);

    expect(await screen.findByTitle('原文件预览：多模态面试')).toHaveAttribute(
      'src',
      'http://localhost:8000/api/knowledge/kb-000000000001/source#page=3',
    );
  });

  it('shows an empty state when there are no entries', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi());

    render(<KnowledgePage />);

    expect(await screen.findByText(/知识库还是空的/)).toBeInTheDocument();
  });

  it('clears the previous document when switching knowledge collections', async () => {
    const firstEntry = { ...entry, title: '通用资料', content: undefined };
    const secondEntry = { ...entry, id: 'kb-000000000002', title: '团队资料' };
    const baseFetch = mockKnowledgeApi([firstEntry], [], [
      { id: 'collection-general', name: '通用资料库' },
      { id: 'collection-team', name: '团队资料库' },
    ]);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/knowledge?collection_id=collection-team')) {
        return { ok: true, json: async () => ({ documents: [secondEntry] }) };
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);
    const firstTitle = await screen.findByText('通用资料', { selector: '.knowledge-item-title' });
    const firstRow = firstTitle.closest('li');
    if (!(firstRow instanceof HTMLElement)) throw new Error('Expected first knowledge row');
    await user.click(within(firstRow).getByRole('button', { name: /通用资料/ }));
    expect(await screen.findByText('多模态大模型结构')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '团队资料库' }));

    expect(await screen.findByText('团队资料')).toBeInTheDocument();
    expect(screen.queryByText('多模态大模型结构')).not.toBeInTheDocument();
  });

  it('keeps advanced maintenance actions behind the more menu', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([], [], [{ id: 'collection-general', name: '通用资料库' }]));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    expect(screen.getByRole('button', { name: '更多操作' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: '导出备份' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '更多操作' }));

    expect(screen.getByRole('button', { name: '更多操作' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: '导出备份' })).toBeInTheDocument();
  });

  it('keeps the search toolbar outside the scrolling content area', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi());

    render(<KnowledgePage />);

    const toolbar = document.querySelector('.knowledge-main-toolbar');
    expect(toolbar?.nextElementSibling).toHaveClass('knowledge-main-scroll');
  });

  it('shows RAG model health and per-document indexing stage', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([{ ...entry, status: 'indexing' } as typeof entry]));

    render(<KnowledgePage />);

    expect(await screen.findByText('RAG 运行状态')).toBeInTheDocument();
    expect(screen.getByText('bge-m3')).toBeInTheDocument();
    expect(await screen.findByText('正在生成向量索引')).toBeInTheDocument();
  });

  it('searches the knowledge base', async () => {
    const fetchMock = mockKnowledgeApi([], [hit]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText(/搜索资料/), '多模态');
    await user.click(screen.getByRole('button', { name: '检索' }));
    expect(await screen.findByText('多模态大模型结构')).toBeInTheDocument();
  });

  it('opens and highlights the source chunk from a retrieval result', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry], [{
      ...hit,
      document_id: entry.id,
      chunk_id: 'chunk-search-2',
      location: '第 2 页',
      routes: ['keyword', 'reranker'],
      score: 0.83,
    }], [], [
      { id: 'chunk-search-2', location: '第 2 页', content: '检索命中的原文内容。' },
    ]));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText(/搜索资料/), '多模态');
    await user.click(screen.getByRole('button', { name: '检索' }));

    await screen.findByText('多模态大模型结构');
    expect(screen.queryByText('关键词 · 重排 · 83%')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开资料：多模态面试' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '打开资料：多模态面试' }));

    const source = await screen.findByText('检索命中的原文内容。');
    expect(source.closest('[data-citation-target]')).toHaveAttribute('data-citation-target', 'true');
  });

  it('anchors the rename menu to the selected knowledge collection', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([], [], [{ id: 'collection-team', name: '团队资料' }]));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    const rename = await screen.findByRole('button', { name: '重命名团队资料' });
    await user.click(rename);

    const row = screen.getByText('团队资料').closest('.knowledge-collection-row');
    expect(row).not.toBeNull();
    if (!(row instanceof HTMLElement)) {
      throw new Error('Expected the knowledge collection row to be an HTML element');
    }
    expect(within(row).getByText('重命名知识库')).toBeInTheDocument();
    expect(rename).not.toHaveTextContent('⌕');
  });

  it('closes the knowledge collection menu when clicking elsewhere', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([], [], [{ id: 'collection-team', name: '团队资料' }]));
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.click(await screen.findByRole('button', { name: '重命名团队资料' }));
    expect(screen.getByText('重命名知识库')).toBeInTheDocument();

    await user.click(document.body);

    expect(screen.queryByText('重命名知识库')).not.toBeInTheDocument();
  });

  it('edits retrieval strategy for the selected knowledge collection', async () => {
    const fetchMock = mockKnowledgeApi([], [], [{ id: 'collection-team', name: '团队资料' }]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.click(await screen.findByRole('button', { name: '配置团队资料检索策略' }));
    await user.clear(await screen.findByLabelText('Top-K'));
    await user.type(screen.getByLabelText('Top-K'), '3');
    await user.click(screen.getByRole('button', { name: '保存检索策略' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/knowledge/collections/collection-team/retrieval-config',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ top_k: 3, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 }) }),
    ));
  });

  it('shows saved evaluation trends and restores an earlier strategy', async () => {
    const fetchMock = mockKnowledgeApi([], [], [], [], [{
      id: 'evaluation-previous', created_at: 1000, total: 2, hit_count: 2, judged_total: 2,
      recall_at_1: 0.5, recall_at_3: 1, mrr: 0.75,
      config: { top_k: 5, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 },
    }]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    expect(await screen.findByText('最近评测趋势')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '回退到此策略' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/knowledge/evaluate/history/evaluation-previous/restore?collection_id=collection-general',
      { method: 'POST' },
    ));
  });

  it('restores the original retrieval strategy when an applied recommendation fails the regression gate', async () => {
    const originalConfig = { top_k: 5, candidate_multiplier: 3, minimum_relevance_score: 0.2, mmr_relevance_weight: 0.7 };
    const failingEvaluation = {
      total: 1, hit_count: 0, judged_total: 1, recall_at_1: 0, recall_at_3: 0, mrr: 0,
      answer_score: null, grounded_rate: null, route_coverage: {},
      quality_gate: { thresholds: { recall_at_1: 0.7, recall_at_3: 0.8, mrr: 0.75 }, passed: false, failures: [{ metric: 'recall_at_1', actual: 0, threshold: 0.7 }] },
      recommendations: [{ field: 'candidate_multiplier' as const, current: 3, suggested: 5, reason: '扩大候选集' }],
      results: [{ question: '发布计划在哪里', expected_title: '发布计划', status: 'miss' as const, top_score: 0, expected_rank: null, hits: [] }],
    };
    const defaultFetch = mockKnowledgeApi([], [], [], [], [], failingEvaluation);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/collections/collection-general/retrieval-config')) {
        return { ok: true, json: async () => ({ config: originalConfig }) };
      }
      return defaultFetch(input, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText(/React 状态管理/), '发布计划在哪里 || 发布计划');
    await user.click(screen.getByRole('button', { name: '运行评测' }));
    await user.click(await screen.findByRole('button', { name: '应用建议并重新评测' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/knowledge/collections/collection-general/retrieval-config',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify(originalConfig) }),
    ));
    expect(await screen.findByText('评测建议未通过回归门禁，已自动恢复原检索策略。')).toBeInTheDocument();
  });

  it('turns a missed evaluation result into a replayable bad case', async () => {
    const fetchMock = mockKnowledgeApi([entry], [], [], [], [], {
      total: 1, hit_count: 0, judged_total: 1, recall_at_1: 0, recall_at_3: 0, mrr: 0,
      answer_score: null, grounded_rate: null, route_coverage: {}, recommendations: [],
      results: [{ question: '发布计划在哪里', expected_title: '发布计划', relevant_chunk_ids: ['chunk-plan'], status: 'miss', top_score: 0, expected_rank: null, hits: [] }],
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    await user.type(screen.getByPlaceholderText(/React 状态管理/), '发布计划在哪里 || 发布计划');
    await user.click(screen.getByRole('button', { name: '运行评测' }));
    await screen.findByText('未命中 · 发布计划在哪里');
    await user.type(screen.getByLabelText('失败原因：发布计划在哪里'), '没有召回发布计划资料');
    await user.click(screen.getByRole('button', { name: '加入 Bad Case' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/bad-cases', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: '发布计划在哪里', collection_id: 'collection-general', expected_title: '发布计划', relevant_chunk_ids: ['chunk-plan'], relevant_document_ids: [], expected_answer: '', actual_answer: '', reason: '没有召回发布计划资料' }),
    }));
  });

  it('merges current bad cases and runs them as one regression evaluation', async () => {
    const fetchMock = mockKnowledgeApi([entry], [], [], [], [], {
      total: 1, hit_count: 1, judged_total: 1, recall_at_1: 1, recall_at_3: 1, mrr: 1,
      answer_score: null, grounded_rate: null, route_coverage: {}, recommendations: [],
      results: [{ question: '发布计划在哪里', expected_title: '发布计划', status: 'pass', top_score: 1, expected_rank: 1, hits: [] }],
    }, [{ id: 'bad-plan', question: '发布计划在哪里', collection_id: 'collection-general', expected_title: '发布计划', reason: '未命中' }]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);

    expect(await screen.findByText('已记录的失败样例')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '合并 1 个 Bad Case' }));
    expect(screen.getByPlaceholderText(/React 状态管理/)).toHaveValue('发布计划在哪里 || 发布计划');
    await user.click(screen.getByRole('button', { name: '批量重放 1 个 Bad Case' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/evaluate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases: [{ question: '发布计划在哪里', expected_title: '发布计划' }], collection_id: 'collection-general' }),
    }));
  });

  it('labels document hits separately from standard chunk retrieval metrics', async () => {
    const fetchMock = mockKnowledgeApi([entry], [], [], [], [], {
      total: 1, hit_count: 1, judged_total: 1, recall_at_1: 0.5, recall_at_3: 1, hit_at_1: 0.5, hit_at_3: 1, mrr: 0.5,
      metrics: {
        k_values: [1, 3, 5],
        hit_rate: { 1: 0.5, 3: 1, 5: 1 },
        recall: { 1: 0.25, 3: 0.75, 5: 1 },
        precision: { 1: 0.5, 3: 0.667, 5: 0.4 },
        ndcg: { 1: 0.5, 3: 0.693, 5: 0.8 },
        mrr: 0.5,
      },
      answer_score: null, grounded_rate: null, route_coverage: {}, recommendations: [],
      results: [{ question: '发布计划在哪里', expected_title: '发布计划', status: 'pass', top_score: 1, expected_rank: 2, hits: [] }],
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);
    const evaluationInput = screen.getByPlaceholderText(/React 状态管理/);
    await user.clear(evaluationInput);
    await user.type(evaluationInput, '发布计划在哪里 || 发布计划 || chunk-1, chunk-2');
    await user.click(screen.getByRole('button', { name: '运行评测' }));

    expect(await screen.findByText(/Hit@1 50% · Hit@3 100% · MRR 0.5/)).toBeInTheDocument();
    expect(screen.getByText(/K=5 · Recall 100% · Precision 40% · NDCG 80%/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/evaluate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases: [{ question: '发布计划在哪里', expected_title: '发布计划', relevant_chunk_ids: ['chunk-1', 'chunk-2'] }], collection_id: 'collection-general' }),
    });
  });

  it('builds a chunk-level evaluation case by selecting retrieved candidates', async () => {
    const candidates: KnowledgeSearchHit[] = [
      { document_id: 'doc-1', chunk_id: 'chunk-1', title: 'Redis 基础', content: '缓存穿透可以使用布隆过滤器。', source_url: null, score: 0.91, routes: ['vector'] },
      { document_id: 'doc-2', chunk_id: 'chunk-2', title: 'Redis 实战', content: '空值缓存也可以缓解缓存穿透。', source_url: null, score: 0.82, routes: ['keyword'] },
    ];
    const fetchMock = mockKnowledgeApi([entry], candidates);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<KnowledgePage />);
    await user.clear(screen.getByPlaceholderText(/React 状态管理/));
    await user.type(screen.getByLabelText('待标注问题'), '缓存穿透怎么解决？');
    await user.click(screen.getByRole('button', { name: '检索候选切片' }));
    await user.click(await screen.findByLabelText('标记切片 chunk-1 为相关'));
    await user.click(screen.getByLabelText('标记切片 chunk-2 为相关'));
    await user.click(screen.getByRole('button', { name: '加入评测集' }));

    expect(screen.getByPlaceholderText(/React 状态管理/)).toHaveValue('缓存穿透怎么解决？ || Redis 基础 || chunk-1,chunk-2');
  });

  it('imports a JSON evaluation dataset into the editable suite', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry]));
    const user = userEvent.setup();
    const file = new File([JSON.stringify({ cases: [{ question: '如何避免缓存雪崩？', expected_title: 'Redis 稳定性', relevant_chunk_ids: ['chunk-a'] }] })], 'rag-evaluation.json', { type: 'application/json' });

    render(<KnowledgePage />);
    await user.upload(screen.getByLabelText('导入评测集'), file);

    expect(screen.getByPlaceholderText(/React 状态管理/)).toHaveValue('如何避免缓存雪崩？ || Redis 稳定性 || chunk-a');
    expect(await screen.findByText('已导入 1 条评测用例。')).toBeInTheDocument();
  });

  it('manages and validates the current collection evaluation suite in a table', async () => {
    const fetchMock = mockKnowledgeApi([entry]);
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<KnowledgePage />);
    const input = screen.getByPlaceholderText(/React 状态管理/);
    await user.clear(input);
    await user.type(input, '发布计划？ || 发布计划 || chunk-stale\n负责人是谁？');

    expect(screen.getByText('已标注 1/50')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '检查评测集' }));

    expect(await screen.findByText('失效切片：chunk-stale')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/evaluate/validate', expect.objectContaining({ method: 'POST' }));
  });

  it('exports the editable evaluation suite as JSON', async () => {
    vi.stubGlobal('fetch', mockKnowledgeApi([entry]));
    const createObjectURL = vi.fn(() => 'blob:evaluation');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const user = userEvent.setup();

    render(<KnowledgePage />);
    const evaluationInput = screen.getByPlaceholderText(/React 状态管理/);
    await user.clear(evaluationInput);
    await user.type(evaluationInput, '缓存穿透怎么办？ || Redis 基础 || chunk-1');
    await user.click(screen.getByRole('button', { name: '导出 JSON' }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:evaluation');
    expect(await screen.findByText('已导出 JSON 评测集。')).toBeInTheDocument();
    click.mockRestore();
  });
});
