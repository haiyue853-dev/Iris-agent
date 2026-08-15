import type { AgentTask, TaskDetail } from '../types';

const API_BASE = 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    if (response.status === 503) throw new Error('任务队列暂不可用，请稍后重试');
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || '任务请求失败');
  }
  return response.json() as Promise<T>;
}

export async function listTasks(): Promise<AgentTask[]> {
  return (await request<{ tasks: AgentTask[] }>('/api/tasks')).tasks;
}

export function getTask(id: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/api/tasks/${encodeURIComponent(id)}`);
}

export function createTask(sessionId: string, message: string): Promise<AgentTask> {
  return request<AgentTask>('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export function cancelTask(id: string): Promise<AgentTask> {
  return request<AgentTask>(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function resolveTaskApproval(taskId: string, callId: string, approved: boolean): Promise<AgentTask> {
  return request<AgentTask>(`/api/tasks/${encodeURIComponent(taskId)}/tool-approvals/${encodeURIComponent(callId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  });
}
