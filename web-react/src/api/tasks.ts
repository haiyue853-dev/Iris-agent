import type { AgentTask, TaskDetail } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error('Task request failed');
  return response.json() as Promise<T>;
}

export async function listTasks(): Promise<AgentTask[]> {
  return (await request<{ tasks: AgentTask[] }>('/api/tasks')).tasks;
}

export function getTask(id: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/api/tasks/${encodeURIComponent(id)}`);
}
