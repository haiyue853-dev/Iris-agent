const API_BASE = 'http://localhost:8000';

export type McpServer = { id: string; name: string; transport: 'stdio' | 'http'; command: string; url: string; args: string[]; allowed_tools: string[]; env_keys: string[]; header_keys: string[]; timeout_seconds: number; enabled: boolean; status: string; discovered_tools: McpTool[] };
export type McpEvent = { server_id: string; kind: 'discovery' | 'tool_call'; tool_name?: string; ok: boolean; duration_ms: number; created_at: number; failure_kind?: 'startup_failed' | 'timeout' | 'protocol_error' | 'tool_error' | 'unknown' };
export type McpTool = { name: string; description?: string; annotations?: { readOnlyHint?: boolean } };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail?.message || 'MCP 请求失败');
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const listMcpServers = () => request<{ servers: McpServer[] }>('/api/mcp/servers');
export const setMcpEnabled = (id: string, enabled: boolean) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/enabled`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
export const createMcpServer = (input: Pick<McpServer, 'name' | 'transport' | 'command' | 'url' | 'args' | 'allowed_tools'> & { headers?: Record<string, string> }) => request<McpServer>('/api/mcp/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
export const discoverMcpTools = (id: string) => request<{ tools: McpTool[]; server: McpServer }>(`/api/mcp/servers/${encodeURIComponent(id)}/discover`, { method: 'POST' });
export const setMcpAllowedTools = (id: string, allowed_tools: string[]) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/allowed-tools`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed_tools }) });
export const setMcpEnvironment = (id: string, environment: Record<string, string>) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/environment`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ environment }) });
export const setMcpTimeout = (id: string, timeout_seconds: number) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/timeout`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ timeout_seconds }) });
export const setMcpHeaders = (id: string, headers: Record<string, string>) => request<McpServer>(`/api/mcp/servers/${encodeURIComponent(id)}/headers`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ headers }) });
export const deleteMcpServer = (id: string) => request<void>(`/api/mcp/servers/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const listMcpEvents = (id: string) => request<{ events: McpEvent[] }>(`/api/mcp/servers/${encodeURIComponent(id)}/events`);
