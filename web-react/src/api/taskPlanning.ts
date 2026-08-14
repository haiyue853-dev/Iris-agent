const API_BASE = 'http://localhost:8000';

export type TaskEvent = { at: number; type: string; details: Record<string, unknown> };
export type TaskStep = { id: string; title: string; instruction: string; status: string; approval_call_id: string | null; result: string; error: string | null; events: TaskEvent[] };
export type TaskPlan = { id: string; session_id: string; goal: string; status: string; steps: TaskStep[]; updated_at: number };
export type Subagent = { id: string; parent_session_id: string; title: string; status: string; allowed_tools: string[]; result: string; error: string | null; updated_at: number };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail?.message || '请求失败');
  return response.json() as Promise<T>;
}

export const listTaskPlans = (sessionId: string) => request<{ items: TaskPlan[] }>(`/api/task-plans?session_id=${encodeURIComponent(sessionId)}`);
export const createAutomaticTaskPlan = (sessionId: string, goal: string) => request<TaskPlan>('/api/task-plans/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId, goal }) });
export const runNextTaskStep = (id: string) => request<{ task: TaskPlan }>(`/api/task-plans/${encodeURIComponent(id)}/run-next`, { method: 'POST' });
export const approveTaskPlan = (id: string, approved: boolean) => request<{ task: TaskPlan }>(`/api/task-plans/${encodeURIComponent(id)}/approval`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }) });
export const delegateTaskStep = (planId: string, stepId: string, allowedTools: string[]) => request<{ task: TaskPlan }>(`/api/task-plans/${encodeURIComponent(planId)}/steps/${encodeURIComponent(stepId)}/delegate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed_tools: allowedTools }) });
export const listSubagents = (sessionId: string) => request<{ items: Subagent[] }>(`/api/subagents?parent_session_id=${encodeURIComponent(sessionId)}`);
