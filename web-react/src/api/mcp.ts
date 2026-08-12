const API_BASE = 'http://localhost:8000';

export type McpServer = { id: string; name: string; command: string; args: string[]; allowed_tools: string[]; enabled: boolean; status: string };
export type McpEvent = { server_id: string; kind: 'discovery' | 'tool_call'; tool_name?: string; ok: boolean; duration_ms: number; created_at: number };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail?.message || 'MCP 请求失败');
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const listMcpServers = () => request<{ servers: McpServer[] }>('/api/mcp/servers');
export const setMcpEnabled = (id: string, enabled: boolean) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/enabled`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
export const createMcpServer = (input: Omit<McpServer, 'id' | 'enabled' | 'status'>) => request<McpServer>('/api/mcp/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
export const discoverMcpTools = (id: string) => request<{ tools: { name: string; description?: string }[] }>(`/api/mcp/servers/${encodeURIComponent(id)}/discover`, { method: 'POST' });
export const setMcpAllowedTools = (id: string, allowed_tools: string[]) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/allowed-tools`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed_tools }) });
export const deleteMcpServer = (id: string) => request<void>(`/api/mcp/servers/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const listMcpEvents = (id: string) => request<{ events: McpEvent[] }>(`/api/mcp/servers/${encodeURIComponent(id)}/events`);
