import type { KnowledgeDetail, KnowledgeEntry, KnowledgeSearchHit } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '知识库请求失败');
  }
  return response.json() as Promise<T>;
}

export type KnowledgeCollection = { id: string; name: string; description: string | null; created_at: number };
export type KnowledgeCollectionRetrievalConfig = { top_k: number; candidate_multiplier: number; minimum_relevance_score: number; mmr_relevance_weight: number };

export async function listKnowledge(collectionId?: string): Promise<KnowledgeEntry[]> {
  const result = await request<{ entries?: KnowledgeEntry[]; documents?: KnowledgeEntry[] }>(`/api/knowledge${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`);
  return result.documents || result.entries || [];
}

export async function createKnowledge(input: {
  title: string;
  content: string;
  category?: string;
  sourceUrl?: string;
  collectionId?: string;
}): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>('/api/knowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      content: input.content,
      category: input.category || '面经',
      source_url: input.sourceUrl || null,
      collection_id: input.collectionId || 'collection-general',
    }),
  });
}

export async function getKnowledge(id: string): Promise<KnowledgeDetail> {
  return request<KnowledgeDetail>(`/api/knowledge/${encodeURIComponent(id)}`);
}
export type KnowledgeChunkRevision = { id: string; chunk_id: string; content: string; location: string | null; created_at: number };
export type KnowledgeChunkMutation = { chunk: { id: string; document_id: string; content: string; location: string | null; ordinal?: number; parent_id?: string | null }; revisions: KnowledgeChunkRevision[]; embedding_updated: boolean };
export async function updateKnowledgeChunk(documentId: string, chunkId: string, content: string, location?: string | null): Promise<KnowledgeChunkMutation> { return request(`/api/knowledge/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, location: location || null }) }); }
export async function getKnowledgeChunkRevisions(documentId: string, chunkId: string): Promise<KnowledgeChunkRevision[]> { return (await request<{ revisions: KnowledgeChunkRevision[] }>(`/api/knowledge/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}/revisions`)).revisions; }
export async function restoreKnowledgeChunkRevision(documentId: string, chunkId: string, revisionId: string): Promise<KnowledgeChunkMutation> { return request(`/api/knowledge/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}/revisions/${encodeURIComponent(revisionId)}/restore`, { method: 'POST' }); }
export const knowledgeSourceUrl = (id: string): string => `${API_BASE}/api/knowledge/${encodeURIComponent(id)}/source`;
export type DocumentMindMapNode = { id: string; parent_id: string | null; label: string; summary: string; kind: 'root' | 'branch' | 'point'; ordinal: number; evidence_chunk_ids: string[] };
export type DocumentMindMapData = { document_id: string; title: string; nodes: DocumentMindMapNode[] };
export async function getKnowledgeMindMap(id: string): Promise<DocumentMindMapData> {
  return request<DocumentMindMapData>(`/api/knowledge/${encodeURIComponent(id)}/mindmap`);
}


export async function updateKnowledge(id: string, title: string, content: string): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>(`/api/knowledge/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, content }) });
}

export async function deleteKnowledge(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/knowledge/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function reindexKnowledge(id: string, vectorsOnly = false): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>(`/api/knowledge/${encodeURIComponent(id)}/reindex${vectorsOnly ? '?vectors_only=true' : ''}`, { method: 'POST' });
}
export async function reindexAllKnowledge(collectionId?: string): Promise<{ queued: number }> {
  return request<{ queued: number }>(`/api/knowledge/reindex${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`, { method: 'POST' });
}
export async function mergeKnowledgeGraph(collectionId?: string): Promise<{ merged: number }> {
  return request<{ merged: number }>(`/api/knowledge/graph/merge${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`, { method: 'POST' });
}
export async function moveKnowledge(id: string, collectionId: string): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>(`/api/knowledge/${encodeURIComponent(id)}/collection`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ collection_id: collectionId }) });
}

export async function searchKnowledge(query: string, limit?: number, collectionId?: string): Promise<KnowledgeSearchHit[]> {
  const params = new URLSearchParams({ query });
  if (limit) params.set('limit', String(limit));
  if (collectionId) params.set('collection_id', collectionId);
  return (await request<{ hits: KnowledgeSearchHit[] }>(`/api/knowledge/search?${params.toString()}`)).hits;
}

export type RetrievalDebugCandidate = {
  rank: number; document_id: string; chunk_id: string; title: string; content: string; location: string | null;
  score: number; keyword_score: number; vector_score: number; graph_score: number; reranker_score: number | null; routes: string[];
};
export type RetrievalDebugStage = { key: 'keyword' | 'graph' | 'vector' | 'fused' | 'reranked' | 'final'; label: string; enabled: boolean; elapsed_ms: number; candidates: RetrievalDebugCandidate[] };
export type RetrievalDebugTrace = {
  query: string; retrieval_query: string; collection_id: string | null; candidate_limit: number; elapsed_ms: number;
  config: KnowledgeCollectionRetrievalConfig; stages: RetrievalDebugStage[]; hits: KnowledgeSearchHit[];
};
export async function debugKnowledgeSearch(query: string, collectionId?: string, limit = 10): Promise<RetrievalDebugTrace> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  if (collectionId) params.set('collection_id', collectionId);
  return request<RetrievalDebugTrace>(`/api/knowledge/search/debug?${params.toString()}`);
}

export async function uploadKnowledge(file: File, title = '', collectionId = 'collection-general'): Promise<KnowledgeEntry> {
  const contentBase64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  return request<KnowledgeEntry>('/api/knowledge/upload', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, original_name: file.name, media_type: file.type || null, content_base64: contentBase64, collection_id: collectionId }),
  });
}

export async function listKnowledgeCollections(): Promise<KnowledgeCollection[]> {
  const result = await request<{ collections?: KnowledgeCollection[] }>('/api/knowledge/collections');
  return Array.isArray(result.collections) ? result.collections : [];
}
export async function exportKnowledge(collectionId?: string): Promise<unknown> { return request(`/api/knowledge/export${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`); }
export type KnowledgeStats = { documents: number; ready: number; indexing: number; failed: number; chunks: number; nodes: number; edges: number };
export async function getKnowledgeStats(collectionId?: string): Promise<KnowledgeStats> { return request<KnowledgeStats>(`/api/knowledge/stats${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`); }
export type KnowledgeRuntimeConfig = {
  embedding_enabled: boolean; embedding_model: string; embedding_base_url: string;
  semantic_split_enabled: boolean; semantic_split_model: string; semantic_split_base_url: string;
  graph_enabled: boolean; graph_model: string; graph_base_url: string;
  image_enabled: boolean; image_model: string; image_base_url: string;
  reranker_enabled: boolean; reranker_provider: 'ollama' | 'api' | 'fastembed' | 'none'; reranker_model: string; reranker_base_url: string;
  mmr_relevance_weight: number;
};
export type KnowledgeRuntimeComponent = {
  key: 'embedding' | 'graph' | 'image' | 'reranker'; label: string; enabled: boolean;
  provider: string; model: string; base_url: string; status: 'untested' | 'connected' | 'failed' | 'disabled';
  message: string; latency_ms: number | null;
};
export type KnowledgeRuntime = { config: KnowledgeRuntimeConfig; components: KnowledgeRuntimeComponent[]; requires_reindex?: boolean };
export type KnowledgeIndexProgress = { document_id: string; stage: 'queued' | 'parsing' | 'chunking' | 'graph' | 'embedding' | 'completed' | 'failed'; message: string; failed_stage?: string; updated_at: number };
export async function getKnowledgeRuntime(): Promise<KnowledgeRuntime> { return request<KnowledgeRuntime>('/api/knowledge/runtime'); }
export async function updateKnowledgeRuntime(config: Partial<KnowledgeRuntimeConfig>): Promise<KnowledgeRuntime> { return request<KnowledgeRuntime>('/api/knowledge/runtime', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) }); }
export async function testKnowledgeRuntime(component?: KnowledgeRuntimeComponent['key']): Promise<{ components: KnowledgeRuntimeComponent[] }> { return request('/api/knowledge/runtime/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(component ? { component } : {}) }); }
export async function getKnowledgeIndexProgress(): Promise<KnowledgeIndexProgress[]> { return (await request<{ items: KnowledgeIndexProgress[] }>('/api/knowledge/index-progress')).items; }
export async function importKnowledgeBackup(file: File, collectionId: string): Promise<{ imported: number }> { const backup = JSON.parse(await file.text()); return request<{ imported: number }>('/api/knowledge/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ backup, collection_id: collectionId }) }); }
export type KnowledgeEvaluationGate = { recall_at_1: number; recall_at_3: number; mrr: number };
export type KnowledgeRetrievalMetrics = { k_values: number[]; hit_rate: Record<string, number>; recall: Record<string, number>; precision: Record<string, number>; ndcg: Record<string, number>; mrr: number | null };
export type KnowledgeEvaluation = { collection_id?: string | null; history_id?: string; total: number; hit_count: number; judged_total: number; recall_at_1: number | null; recall_at_3: number | null; hit_at_1?: number | null; hit_at_3?: number | null; metrics?: KnowledgeRetrievalMetrics; mrr: number | null; answer_score: number | null; grounded_rate: number | null; quality_gate?: { thresholds: KnowledgeEvaluationGate | null; passed: boolean | null; failures: Array<{ metric: keyof KnowledgeEvaluationGate; actual: number; threshold: number }> }; route_coverage: Record<string, number>; recommendations: Array<{ field: 'candidate_multiplier' | 'mmr_relevance_weight'; current: number; suggested: number; reason: string }>; results: Array<{ question: string; expected_title?: string | null; expected_document_id?: string | null; relevant_document_ids?: string[]; relevant_chunk_ids?: string[]; expected_answer?: string | null; status: 'pass' | 'hit' | 'miss'; top_score: number; expected_rank?: number | null; answer_quality?: { answer: string; answer_score: number | null; grounded: boolean | null; reason: string } | null; hits: Array<{ title: string; document_id: string; chunk_id?: string; score: number; excerpt: string; routes: string[] }> }> };
export type KnowledgeEvaluationCase = { question: string; expected_title?: string; expected_document_id?: string; relevant_document_ids?: string[]; relevant_chunk_ids?: string[]; relevant_titles?: string[]; expected_answer?: string };
export type KnowledgeEvaluationCaseValidation = { summary: { total: number; annotated: number; duplicates: number; empty_annotations: number; invalid_chunks: number }; rows: Array<{ index: number; duplicate: boolean; empty_annotation: boolean; invalid_chunk_ids: string[] }> };
export type KnowledgeEvaluationHistoryItem = { id: string; created_at: number; total: number; hit_count: number; judged_total: number; recall_at_1: number | null; recall_at_3: number | null; hit_at_1?: number | null; hit_at_3?: number | null; metrics?: KnowledgeRetrievalMetrics; mrr: number | null; config: KnowledgeCollectionRetrievalConfig };
export async function evaluateKnowledge(cases: KnowledgeEvaluationCase[], collectionId?: string): Promise<KnowledgeEvaluation> { return request<KnowledgeEvaluation>('/api/knowledge/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cases, collection_id: collectionId || null }) }); }
export async function generateKnowledgeEvaluation(collectionId?: string): Promise<{ cases: Array<{ question: string; expected_title: string; expected_answer?: string }>; generated_by: 'ollama' | 'fallback' | 'none' }> { return request('/api/knowledge/evaluate/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ collection_id: collectionId || null }) }); }
export async function getKnowledgeEvaluationCases(collectionId?: string): Promise<KnowledgeEvaluationCase[]> { return (await request<{ cases?: KnowledgeEvaluationCase[] }>(`/api/knowledge/evaluate/seed${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`)).cases || []; }
export async function saveKnowledgeEvaluationCases(cases: KnowledgeEvaluationCase[], collectionId?: string): Promise<{ count: number }> { return request('/api/knowledge/evaluate/seed', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cases, collection_id: collectionId || null }) }); }
export async function validateKnowledgeEvaluationCases(cases: KnowledgeEvaluationCase[], collectionId?: string): Promise<KnowledgeEvaluationCaseValidation> { return request('/api/knowledge/evaluate/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cases, collection_id: collectionId || null }) }); }
export async function getKnowledgeEvaluationHistory(collectionId: string): Promise<KnowledgeEvaluationHistoryItem[]> { return (await request<{ items?: KnowledgeEvaluationHistoryItem[] }>(`/api/knowledge/evaluate/history?collection_id=${encodeURIComponent(collectionId)}`)).items || []; }
export async function restoreKnowledgeEvaluationConfig(collectionId: string, historyId: string): Promise<KnowledgeCollectionRetrievalConfig> { return (await request<{ config: KnowledgeCollectionRetrievalConfig }>(`/api/knowledge/evaluate/history/${encodeURIComponent(historyId)}/restore?collection_id=${encodeURIComponent(collectionId)}`, { method: 'POST' })).config; }
export async function getKnowledgeEvaluationGate(collectionId: string): Promise<KnowledgeEvaluationGate> { return (await request<{ thresholds: KnowledgeEvaluationGate }>(`/api/knowledge/evaluate/gate?collection_id=${encodeURIComponent(collectionId)}`)).thresholds; }
export async function updateKnowledgeEvaluationGate(collectionId: string, thresholds: KnowledgeEvaluationGate): Promise<KnowledgeEvaluationGate> { return (await request<{ thresholds: KnowledgeEvaluationGate }>(`/api/knowledge/evaluate/gate?collection_id=${encodeURIComponent(collectionId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(thresholds) })).thresholds; }
export type KnowledgeBadCase = { id?: string; created_at?: number; question: string; collection_id?: string | null; expected_title?: string | null; relevant_chunk_ids?: string[]; relevant_document_ids?: string[]; expected_answer?: string; actual_answer?: string; reason?: string };
export async function getKnowledgeBadCases(): Promise<KnowledgeBadCase[]> { return (await request<{ cases?: KnowledgeBadCase[] }>('/api/knowledge/bad-cases')).cases || []; }
export async function recordKnowledgeBadCase(badCase: KnowledgeBadCase): Promise<KnowledgeBadCase> { return request<KnowledgeBadCase>('/api/knowledge/bad-cases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(badCase) }); }
export async function replayKnowledgeBadCase(id: string): Promise<{ case: KnowledgeBadCase; evaluation: KnowledgeEvaluation }> { return request(`/api/knowledge/bad-cases/${encodeURIComponent(id)}/replay`, { method: 'POST' }); }
export type DuplicateSuggestion = { left: { id: string; title: string }; right: { id: string; title: string }; score: number; reason: string };
export async function getKnowledgeDuplicates(collectionId?: string): Promise<DuplicateSuggestion[]> { return (await request<{ suggestions: DuplicateSuggestion[] }>(`/api/knowledge/duplicates${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`)).suggestions; }
export async function createKnowledgeCollection(name: string, description?: string): Promise<KnowledgeCollection> {
  return request('/api/knowledge/collections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description: description || null }) });
}
export async function deleteKnowledgeCollection(id: string): Promise<void> { await request<{ ok: boolean }>(`/api/knowledge/collections/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
export async function renameKnowledgeCollection(id: string, name: string): Promise<KnowledgeCollection> {
  return request<KnowledgeCollection>(`/api/knowledge/collections/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
}
export async function getKnowledgeCollectionRetrievalConfig(id: string): Promise<KnowledgeCollectionRetrievalConfig> {
  return (await request<{ config: KnowledgeCollectionRetrievalConfig }>(`/api/knowledge/collections/${encodeURIComponent(id)}/retrieval-config`)).config;
}
export async function updateKnowledgeCollectionRetrievalConfig(id: string, config: KnowledgeCollectionRetrievalConfig): Promise<KnowledgeCollectionRetrievalConfig> {
  return (await request<{ config: KnowledgeCollectionRetrievalConfig }>(`/api/knowledge/collections/${encodeURIComponent(id)}/retrieval-config`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) })).config;
}
export async function applyKnowledgeEvaluationRecommendation(id: string, recommendation: { field: 'candidate_multiplier' | 'mmr_relevance_weight'; suggested: number }): Promise<KnowledgeCollectionRetrievalConfig> {
  return (await request<{ config: KnowledgeCollectionRetrievalConfig }>(`/api/knowledge/collections/${encodeURIComponent(id)}/retrieval-config`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [recommendation.field]: recommendation.suggested }) })).config;
}
export async function listKnowledgeTopics(collectionId?: string): Promise<string[]> {
  const result = await request<{ topics?: string[] }>(`/api/knowledge/topics${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`);
  return Array.isArray(result.topics) ? result.topics : [];
}
export async function getKnowledgeGraph(topic?: string, collectionId?: string): Promise<{ nodes: { id: string; label: string; kind: string; document_count: number }[]; edges: { source: string; target: string; relation: string; document_id?: string; confidence?: number; evidence?: string | null; evidence_chunk_id?: string | null }[] }> {
  const params = new URLSearchParams(); if (topic) params.set('topic', topic); if (collectionId) params.set('collection_id', collectionId);
  const result = await request<{ nodes?: { id: string; label: string; kind: string; document_count: number }[]; edges?: { source: string; target: string; relation: string; document_id?: string; confidence?: number; evidence?: string | null; evidence_chunk_id?: string | null }[] }>(`/api/knowledge/graph${params.size ? `?${params}` : ''}`);
  return { nodes: Array.isArray(result.nodes) ? result.nodes : [], edges: Array.isArray(result.edges) ? result.edges : [] };
}
export type GraphSummary = { label: string; summary: string; evidence_count: number; facts: Array<{ source: string; target: string; relation: string; confidence: number }> };
export async function summarizeKnowledgeGraph(input: { kind: 'entity'; node_id: string; collection_id?: string } | { kind: 'relation'; source_id: string; target_id: string; relation: string; document_id?: string; collection_id?: string }): Promise<GraphSummary> { return request<GraphSummary>('/api/knowledge/graph/summarize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) }); }
export type GraphAudit = { counts: { low_confidence: number; missing_evidence: number; similar_labels: number }; low_confidence: Array<{ source: string; target: string; relation: string; document_id: string; confidence: number }>; missing_evidence: Array<{ source: string; target: string; relation: string; document_id: string; confidence: number }>; similar_labels: string[][] };
export async function auditKnowledgeGraph(collectionId?: string): Promise<GraphAudit> { return request<GraphAudit>(`/api/knowledge/graph/audit${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`); }
type GraphRelationInput = { source_id: string; target_id: string; relation: string; document_id?: string };
export async function updateKnowledgeGraphRelation(input: GraphRelationInput & { new_relation: string }): Promise<{ updated: number }> { return request('/api/knowledge/graph/relation', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) }); }
export async function deleteKnowledgeGraphRelation(input: GraphRelationInput): Promise<{ deleted: number }> { return request('/api/knowledge/graph/relation', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) }); }
export async function renameKnowledgeGraphEntity(nodeId: string, label: string, collectionId: string): Promise<{ updated: number }> { return request('/api/knowledge/graph/entity', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ node_id: nodeId, label, collection_id: collectionId }) }); }
export async function deleteKnowledgeGraphEntity(nodeId: string, collectionId: string): Promise<{ deleted: number }> { return request('/api/knowledge/graph/entity', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ node_id: nodeId, collection_id: collectionId }) }); }
