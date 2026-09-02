import type { AgentEvent, Message, Session } from '../types';
import type { Toolset } from '../lib/capability-mode';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

export async function streamChat(sessionId: string, message: string, signal: AbortSignal, onEvent: (event: AgentEvent) => void, attachmentIds: string[] = [], knowledgeCollectionId?: string, knowledgeQueryMode = 'mix', useKnowledge = false, regenerateFromMessageId?: string | null, responseMode: 'fast' | 'thinking' = 'fast', toolsets?: Toolset[], skillId?: string): Promise<void> {
  const response = await checked(await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message, attachment_ids: attachmentIds, knowledge_collection_id: knowledgeCollectionId || null, knowledge_query_mode: knowledgeQueryMode, use_knowledge: useKnowledge, regenerate_from_message_id: regenerateFromMessageId || null, response_mode: responseMode, toolsets, skill_id: skillId || null }), signal,
  }));
  const reader = response.body?.getReader();
  if (!reader) throw new Error('服务器未返回响应流');
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as AgentEvent);
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AgentEvent);
}

export async function streamToolApproval(sessionId: string, callId: string, approved: boolean, signal: AbortSignal, onEvent: (event: AgentEvent) => void): Promise<void> {
  const response = await checked(await fetch(`${API_BASE}/api/sessions/${sessionId}/tool-approvals/${callId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }), signal,
  }));
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Server did not return a response stream');
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as AgentEvent);
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AgentEvent);
}

export async function listSessions(): Promise<Session[]> {
  const data = await (await checked(await fetch(`${API_BASE}/api/sessions`))).json();
  return data.sessions;
}
export async function createSession(name: string, modelProfileId?: string | null): Promise<Session> {
  return (await checked(await fetch(`${API_BASE}/api/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, model_profile_id: modelProfileId || null }) }))).json();
}
export async function getSession(id: string): Promise<{ messages: Message[]; model_profile_id?: string | null }> {
  return (await checked(await fetch(`${API_BASE}/api/sessions/${id}`))).json();
}
export async function setSessionModelProfile(id: string, modelProfileId: string | null): Promise<Session> {
  return (await checked(await fetch(`${API_BASE}/api/sessions/${id}/model-profile`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_profile_id: modelProfileId }) }))).json();
}
export async function deleteSession(id: string): Promise<void> {
  await checked(await fetch(`${API_BASE}/api/sessions/${id}`, { method: 'DELETE' }));
}
