const API_BASE = 'http://localhost:8000';

export type AvailableTool = {
  name: string;
  description: string;
  requires_approval: boolean;
};

export async function listAvailableTools(): Promise<AvailableTool[]> {
  const response = await fetch(`${API_BASE}/api/tools`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  const data = await response.json();
  return (data.tools ?? []) as AvailableTool[];
}
