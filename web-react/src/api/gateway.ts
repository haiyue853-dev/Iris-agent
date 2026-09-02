const API_BASE = 'http://localhost:8000';

export type MessageChannel = {
  id: 'qq';
  name: string;
  enabled: boolean;
  connected: boolean;
  transport: string;
  websocket_path: string;
};

export type NapCatStatus = {
  path: string;
  configured: boolean;
  running: boolean;
  already_running?: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '消息渠道请求失败');
  }
  return response.json() as Promise<T>;
}

export async function listMessageChannels(): Promise<MessageChannel[]> {
  return (await request<{ channels: MessageChannel[] }>('/api/gateway/channels')).channels;
}

export function sendQQTestMessage(userId: string, text = 'Iris QQ 连接测试'): Promise<{ ok: boolean }> {
  return request('/api/gateway/qq/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, text }),
  });
}

export function getNapCatStatus(): Promise<NapCatStatus> {
  return request('/api/gateway/napcat');
}

export function saveNapCatPath(path: string): Promise<NapCatStatus> {
  return request('/api/gateway/napcat', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
}

export function openNapCat(): Promise<NapCatStatus> {
  return request('/api/gateway/napcat/open', { method: 'POST' });
}

export function matchNapCatDirectory(directory: string): Promise<NapCatStatus> {
  return request('/api/gateway/napcat/match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory }),
  });
}

export function websocketAddress(path: string): string {
  return `${API_BASE.replace(/^http/, 'ws')}${path}`;
}
