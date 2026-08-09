import type { WorldNewsItem } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 世界时政热点列表 */
export async function fetchWorldNews(): Promise<WorldNewsItem[]> {
  const response = await checked(await fetch(`${API_BASE}/api/world-news/latest`));
  const data = (await response.json()) as { items: WorldNewsItem[] };
  return data.items;
}
