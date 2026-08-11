import { afterEach, describe, expect, it, vi } from 'vitest';

import { DocumentApiError, saveDocumentDraft, uploadDocument } from './documents';

describe('documents API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uploads a document as multipart form data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 'a6b23452-1b5c-43af-a0b5-7cf5c29aa7ec',
      original_name: 'brief.md',
      suffix: '.md',
      media_type: 'text/markdown',
      size_bytes: 5,
      created_at: 1,
      extraction_status: 'ready',
      text_truncated: false,
      sources: [],
    }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await uploadDocument(new File(['brief'], 'brief.md', { type: 'text/markdown' }));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/documents',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    );
  });

  it('keeps the stable server error code when saving conflicts', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'document_revision_conflict', message: '草稿版本已变化' },
    }), { status: 409 })));

    await expect(saveDocumentDraft('draft-1', '标题', '# 内容', 1)).rejects.toEqual(
      expect.objectContaining<Partial<DocumentApiError>>({
        code: 'document_revision_conflict',
        status: 409,
        message: '草稿版本已变化',
      }),
    );
  });
});
