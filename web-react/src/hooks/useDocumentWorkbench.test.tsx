import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DocumentApiError } from '../api/documents';
import * as documentsApi from '../api/documents';
import { useDocumentWorkbench } from './useDocumentWorkbench';

vi.mock('../api/documents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/documents')>();
  return {
    ...actual,
    listDocuments: vi.fn(),
    listDocumentDrafts: vi.fn(),
    generateDocumentDraft: vi.fn(),
    saveDocumentDraft: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    getDocumentDraft: vi.fn(),
  };
});

const readyDocument = {
  id: 'a6b23452-1b5c-43af-a0b5-7cf5c29aa7ec', original_name: 'brief.md', suffix: '.md', media_type: 'text/markdown',
  size_bytes: 5, created_at: 1, extraction_status: 'ready' as const, text_truncated: false, sources: [],
};
const pendingDocument = { ...readyDocument, id: '9f2f7cd5-0f67-4db7-96a4-b7d1ac432817', original_name: 'pending.pdf', extraction_status: 'pending' as const };
const generatedDraft = {
  id: 'badb95ed-47db-4a6b-938a-3fece69d9d41', title: '产品需求文档', template: 'prd' as const,
  document_ids: [readyDocument.id], instructions: '', markdown: '# 产品需求文档', citations: [], revision: 1, created_at: 1, updated_at: 1,
};

describe('useDocumentWorkbench', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(documentsApi.listDocuments).mockResolvedValue([readyDocument, pendingDocument]);
    vi.mocked(documentsApi.listDocumentDrafts).mockResolvedValue([]);
  });

  it('generates from ready selected documents and opens the new draft', async () => {
    vi.mocked(documentsApi.generateDocumentDraft).mockResolvedValue(generatedDraft);
    const { result } = renderHook(() => useDocumentWorkbench());
    await waitFor(() => expect(result.current.ready).toBe(true));

    act(() => result.current.toggleDocument(readyDocument.id));
    act(() => result.current.toggleDocument(pendingDocument.id));
    await act(async () => { await result.current.generate(); });

    expect(documentsApi.generateDocumentDraft).toHaveBeenCalledWith('prd', [readyDocument.id], '');
    expect(result.current.draft?.id).toBe(generatedDraft.id);
    expect(result.current.mobilePane).toBe('editor');
  });

  it('retains local edits when save reports a revision conflict', async () => {
    vi.mocked(documentsApi.listDocumentDrafts).mockResolvedValue([generatedDraft]);
    vi.mocked(documentsApi.saveDocumentDraft).mockRejectedValue(
      new DocumentApiError('document_revision_conflict', '草稿版本已变化', 409),
    );
    const { result } = renderHook(() => useDocumentWorkbench());
    await waitFor(() => expect(result.current.draft?.id).toBe(generatedDraft.id));

    act(() => result.current.setMarkdown('# 本地内容'));
    await act(async () => { await result.current.save(); });

    expect(result.current.saveState).toBe('conflict');
    expect(result.current.markdown).toBe('# 本地内容');
  });
});
