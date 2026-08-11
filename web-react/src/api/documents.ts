import type { DocumentDraft, DocumentTemplate, WorkbenchDocument } from '../types';

const API_BASE = 'http://localhost:8000';

export class DocumentApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'DocumentApiError';
    this.code = code;
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new DocumentApiError(
      body.detail?.code || 'document_request_failed',
      body.detail?.message || `请求失败 (${response.status})`,
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

const jsonRequest = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function listDocuments(): Promise<WorkbenchDocument[]> {
  return (await requestJson<{ documents: WorkbenchDocument[] }>('/api/documents')).documents;
}

export function uploadDocument(file: File): Promise<WorkbenchDocument> {
  const body = new FormData();
  body.append('file', file);
  return requestJson('/api/documents', { method: 'POST', body });
}

export function deleteDocument(id: string): Promise<void> {
  return fetch(`${API_BASE}/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
    .then(async (response) => {
      if (response.ok) return;
      const body = await response.json().catch(() => ({}));
      throw new DocumentApiError(
        body.detail?.code || 'document_request_failed',
        body.detail?.message || `请求失败 (${response.status})`,
        response.status,
      );
    });
}

export async function listDocumentDrafts(): Promise<DocumentDraft[]> {
  return (await requestJson<{ drafts: DocumentDraft[] }>('/api/documents/drafts')).drafts;
}

export function getDocumentDraft(id: string): Promise<DocumentDraft> {
  return requestJson(`/api/documents/drafts/${encodeURIComponent(id)}`);
}

export function generateDocumentDraft(template: DocumentTemplate, documentIds: string[], instructions: string): Promise<DocumentDraft> {
  return requestJson('/api/documents/drafts/generate', jsonRequest('POST', {
    template,
    document_ids: documentIds,
    instructions,
  }));
}

export function saveDocumentDraft(id: string, title: string, markdown: string, expectedRevision: number): Promise<DocumentDraft> {
  return requestJson(`/api/documents/drafts/${encodeURIComponent(id)}`, jsonRequest('PUT', {
    title,
    markdown,
    expected_revision: expectedRevision,
  }));
}

export function documentDraftExportUrl(id: string, format: 'markdown' | 'docx'): string {
  return `${API_BASE}/api/documents/drafts/${encodeURIComponent(id)}/export?format=${format}`;
}
