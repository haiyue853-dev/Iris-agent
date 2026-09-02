import { afterEach, describe, expect, it, vi } from 'vitest';

import { applyKnowledgeEvaluationRecommendation, debugKnowledgeSearch, getKnowledgeBadCases, getKnowledgeChunkRevisions, getKnowledgeEvaluationHistory, getKnowledgeEvaluationCases, getKnowledgeIndexProgress, getKnowledgeRuntime, recordKnowledgeBadCase, replayKnowledgeBadCase, restoreKnowledgeChunkRevision, restoreKnowledgeEvaluationConfig, saveKnowledgeEvaluationCases, testKnowledgeRuntime, updateKnowledgeChunk, updateKnowledgeRuntime, validateKnowledgeEvaluationCases } from './knowledge';

describe('knowledge runtime API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('loads, updates and tests the RAG runtime', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ config: {}, components: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await getKnowledgeRuntime();
    await updateKnowledgeRuntime({ embedding_enabled: false });
    await testKnowledgeRuntime('embedding');
    await getKnowledgeIndexProgress();

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/knowledge/runtime', undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/knowledge/runtime', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ embedding_enabled: false }),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://localhost:8000/api/knowledge/runtime/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ component: 'embedding' }),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(4, 'http://localhost:8000/api/knowledge/index-progress', undefined);
  });

  it('loads and saves a collection evaluation suite', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cases: [{ question: '发布计划', expected_title: '路线图' }] }) });
    vi.stubGlobal('fetch', fetchMock);

    await getKnowledgeEvaluationCases('collection-team');
    await saveKnowledgeEvaluationCases([{ question: '发布计划', expected_title: '路线图' }], 'collection-team');

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/knowledge/evaluate/seed?collection_id=collection-team', undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/knowledge/evaluate/seed', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases: [{ question: '发布计划', expected_title: '路线图' }], collection_id: 'collection-team' }),
    });
  });

  it('validates a collection evaluation suite', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary: {}, rows: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await validateKnowledgeEvaluationCases([{ question: '发布计划', relevant_chunk_ids: ['chunk-1'] }], 'collection-team');

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/evaluate/validate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases: [{ question: '发布计划', relevant_chunk_ids: ['chunk-1'] }], collection_id: 'collection-team' }),
    });
  });

  it('edits a chunk and manages its revision history', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ chunk: {}, revisions: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await updateKnowledgeChunk('doc-1', 'chunk-1', '修正内容', '人工修订');
    await getKnowledgeChunkRevisions('doc-1', 'chunk-1');
    await restoreKnowledgeChunkRevision('doc-1', 'chunk-1', 'revision-1');

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/knowledge/doc-1/chunks/chunk-1', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: '修正内容', location: '人工修订' }),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/knowledge/doc-1/chunks/chunk-1/revisions', undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://localhost:8000/api/knowledge/doc-1/chunks/chunk-1/revisions/revision-1/restore', { method: 'POST' });
  });

  it('loads a staged retrieval trace', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ query: 'RAG', stages: [], hits: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await debugKnowledgeSearch('RAG 调试', 'collection-team', 10);

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/search/debug?query=RAG+%E8%B0%83%E8%AF%95&limit=10&collection_id=collection-team', undefined);
  });

  it('applies one recommended setting to its collection', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ config: { candidate_multiplier: 4 } }) });
    vi.stubGlobal('fetch', fetchMock);

    await applyKnowledgeEvaluationRecommendation('collection-team', { field: 'candidate_multiplier', suggested: 4 });

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/collections/collection-team/retrieval-config', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_multiplier: 4 }),
    });
  });

  it('loads evaluation trends and restores a strategy snapshot', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await getKnowledgeEvaluationHistory('collection-team');
    await restoreKnowledgeEvaluationConfig('collection-team', 'evaluation-123');

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/knowledge/evaluate/history?collection_id=collection-team', undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/knowledge/evaluate/history/evaluation-123/restore?collection_id=collection-team', { method: 'POST' });
  });

  it('records and replays failed evaluation cases', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ cases: [] }) });
    vi.stubGlobal('fetch', fetchMock);
    const badCase = { question: '发布计划', collection_id: 'collection-team', expected_title: '路线图', expected_answer: '', actual_answer: '', reason: '未命中' };

    await getKnowledgeBadCases();
    await recordKnowledgeBadCase(badCase);
    await replayKnowledgeBadCase('bad-123');

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/knowledge/bad-cases', undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/knowledge/bad-cases', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(badCase),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://localhost:8000/api/knowledge/bad-cases/bad-123/replay', { method: 'POST' });
  });
});
