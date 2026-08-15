import type { MemoryCategory, MemoryEntry } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '记忆请求失败');
  }
  return response.json() as Promise<T>;
}

export async function listMemories(): Promise<MemoryEntry[]> {
  return (await request<{ entries: MemoryEntry[] }>('/api/memory')).entries;
}

export async function createMemory(content: string, category: MemoryCategory): Promise<MemoryEntry> {
  return request<MemoryEntry>('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, category }),
  });
}

export async function deleteMemory(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
