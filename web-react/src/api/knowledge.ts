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

export async function listKnowledge(): Promise<KnowledgeEntry[]> {
  return (await request<{ entries: KnowledgeEntry[] }>('/api/knowledge')).entries;
}

export async function createKnowledge(input: {
  title: string;
  content: string;
  category?: string;
  sourceUrl?: string;
}): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>('/api/knowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      content: input.content,
      category: input.category || '面经',
      source_url: input.sourceUrl || null,
    }),
  });
}

export async function getKnowledge(id: string): Promise<KnowledgeDetail> {
  return request<KnowledgeDetail>(`/api/knowledge/${encodeURIComponent(id)}`);
}

export async function deleteKnowledge(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/knowledge/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function searchKnowledge(query: string, limit?: number): Promise<KnowledgeSearchHit[]> {
  const params = new URLSearchParams({ query });
  if (limit) params.set('limit', String(limit));
  return (await request<{ hits: KnowledgeSearchHit[] }>(`/api/knowledge/search?${params.toString()}`)).hits;
}
