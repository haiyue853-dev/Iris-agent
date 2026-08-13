const API_BASE = 'http://localhost:8000';

export type AutomationTask = { id: string; name: string; schedule: string; enabled: boolean };
export type AutomationExecution = { id: string; task_id: string; trigger: string; status: 'running' | 'succeeded' | 'failed' | 'unknown'; summary: string; new_count: number; failed_sources: string[]; item_ids: string[] };
export type RadarSubscription = { id: string; keyword: string };
export type RadarItem = { id: string; title: string; url: string; source: string; summary: string; keyword: string };
export type Notification = { id: string; title: string; summary: string; task_id: string; item_ids: string[]; read: boolean };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail?.message || '请求失败');
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const listAutomationTasks = () => request<{ tasks: AutomationTask[] }>('/api/automation/tasks');
export const createAutomationTask = (name: string, schedule: string) => request<AutomationTask>('/api/automation/tasks', json({ name, schedule }));
export const setAutomationTaskEnabled = (id: string, enabled: boolean) => request<AutomationTask>(`/api/automation/tasks/${encodeURIComponent(id)}/enabled`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
export const runAutomationTask = (id: string) => request<AutomationExecution>(`/api/automation/tasks/${encodeURIComponent(id)}/run`, { method: 'POST' });
export const listTaskExecutions = (id: string) => request<{ executions: AutomationExecution[] }>(`/api/automation/tasks/${encodeURIComponent(id)}/executions`);
export const listRadarSubscriptions = () => request<{ subscriptions: RadarSubscription[] }>('/api/hot-radar/subscriptions');
export const createRadarSubscription = (keyword: string) => request<RadarSubscription>('/api/hot-radar/subscriptions', json({ keyword }));
export const deleteRadarSubscription = (id: string) => request<void>(`/api/hot-radar/subscriptions/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const listRadarItems = () => request<{ items: RadarItem[] }>('/api/hot-radar/items');
export const deleteAutomationTask = (id: string) => request<void>(`/api/automation/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const listNotifications = () => request<{ notifications: Notification[] }>('/api/notifications');
export const markNotificationRead = (id: string) => request<Notification>(`/api/notifications/${encodeURIComponent(id)}/read`, { method: 'PUT' });
export const deleteNotification = (id: string) => request<void>(`/api/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' });
