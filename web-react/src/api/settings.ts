import type { SettingsState } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 读取当前 AI 配置状态（key 为掩码） */
export async function fetchSettings(): Promise<SettingsState> {
  const response = await checked(await fetch(`${API_BASE}/api/settings`));
  return (await response.json()) as SettingsState;
}

/** 保存配置（仅提交要修改的字段；保存后立即生效） */
export async function updateSettings(patch: { api_key?: string; base_url?: string; model?: string }): Promise<SettingsState> {
  const response = await checked(await fetch(`${API_BASE}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }));
  return (await response.json()) as SettingsState;
}
