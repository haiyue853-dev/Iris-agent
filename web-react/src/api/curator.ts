import type { CuratorReport, CuratorReportSummary } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '审查请求失败');
  }
  return response.json() as Promise<T>;
}

export async function runCurator(): Promise<CuratorReport> {
  return request<CuratorReport>('/api/curator/run', { method: 'POST' });
}

export async function listCuratorReports(): Promise<CuratorReportSummary[]> {
  return (await request<{ reports: CuratorReportSummary[] }>('/api/curator/reports')).reports;
}

export async function getCuratorReport(id: string): Promise<CuratorReport> {
  return request<CuratorReport>(`/api/curator/reports/${encodeURIComponent(id)}`);
}

export async function applyCuratorSuggestion(reportId: string, suggestionIds?: string[]): Promise<{ applied: number }> {
  return request<{ applied: number }>(`/api/curator/reports/${encodeURIComponent(reportId)}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(suggestionIds ? { suggestion_ids: suggestionIds } : { all: true }),
  });
}

export async function dismissCuratorSuggestion(reportId: string, suggestionIds?: string[]): Promise<{ dismissed: number }> {
  return request<{ dismissed: number }>(`/api/curator/reports/${encodeURIComponent(reportId)}/dismiss`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(suggestionIds ? { suggestion_ids: suggestionIds } : { all: true }),
  });
}
