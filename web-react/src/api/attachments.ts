import type { ChatAttachment } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `附件请求失败 (${response.status})`);
  }
  return response;
}

export async function uploadAttachment(sessionId: string, file: File): Promise<ChatAttachment> {
  const form = new FormData();
  form.append('file', file);
  const response = await checked(await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/attachments`, { method: 'POST', body: form }));
  return (await response.json()).attachment as ChatAttachment;
}

export async function listAttachments(sessionId: string): Promise<ChatAttachment[]> {
  const response = await checked(await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/attachments`));
  return ((await response.json()).attachments ?? []) as ChatAttachment[];
}

export async function deleteAttachment(sessionId: string, attachmentId: string): Promise<void> {
  await checked(await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' }));
}

export function attachmentDownloadUrl(sessionId: string, attachmentId: string): string {
  return `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}/download`;
}
