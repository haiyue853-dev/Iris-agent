import type { AihotDailyReport } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 最新一期日报（当日未生成自动回退最近一期） */
export async function fetchLatestDaily(): Promise<AihotDailyReport> {
  const response = await checked(await fetch(`${API_BASE}/api/aihot-daily/latest`));
  return (await response.json()) as AihotDailyReport;
}

/** 指定日期日报 */
export async function fetchDailyByDate(date: string): Promise<AihotDailyReport> {
  const response = await checked(await fetch(`${API_BASE}/api/aihot-daily/${date}`));
  return (await response.json()) as AihotDailyReport;
}

/** 指定日期的 Markdown 简报 */
export async function fetchDailyMarkdown(date: string): Promise<{ markdown: string; is_fallback: boolean }> {
  const response = await checked(await fetch(`${API_BASE}/api/aihot-daily/${date}/markdown`));
  return (await response.json()) as { markdown: string; is_fallback: boolean };
}
