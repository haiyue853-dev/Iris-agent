import type { TechNewsItem } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 计算机行业新闻列表（IT之家 + 网易科技） */
export async function fetchTechNews(): Promise<TechNewsItem[]> {
  const response = await checked(await fetch(`${API_BASE}/api/tech-news/latest`));
  const data = (await response.json()) as { items: TechNewsItem[] };
  return data.items;
}
