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
  const result = await request<{ entries?: KnowledgeEntry[]; documents?: KnowledgeEntry[] }>('/api/knowledge');
  return result.documents || result.entries || [];
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

export async function uploadKnowledge(file: File, title = ''): Promise<KnowledgeEntry> {
  const contentBase64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  return request<KnowledgeEntry>('/api/knowledge/upload', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, original_name: file.name, media_type: file.type || null, content_base64: contentBase64 }),
  });
}

export async function listKnowledgeTopics(): Promise<string[]> { return (await request<{ topics: string[] }>('/api/knowledge/topics')).topics; }
export async function getKnowledgeGraph(topic?: string): Promise<{ nodes: { id: string; label: string; kind: string; document_count: number }[]; edges: { source: string; target: string; relation: string }[] }> {
  return request(`/api/knowledge/graph${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`);
}
