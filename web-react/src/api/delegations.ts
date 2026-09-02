import type { DelegationDetail, DelegationSummary } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '后台委派请求失败');
  }
  return response.json() as Promise<T>;
}

export async function listDelegations(): Promise<DelegationSummary[]> {
  return (await request<{ delegations: DelegationSummary[] }>('/api/delegations')).delegations;
}

export function getDelegation(id: string): Promise<DelegationDetail> {
  return request<DelegationDetail>(`/api/delegations/${encodeURIComponent(id)}`);
}

export function cancelDelegation(id: string): Promise<DelegationDetail> {
  return request<DelegationDetail>(`/api/delegations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
