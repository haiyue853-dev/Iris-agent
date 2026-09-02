import { afterEach, describe, expect, it, vi } from 'vitest';
import { getKnowledgeMindMap } from './knowledge';

afterEach(() => vi.unstubAllGlobals());

describe('getKnowledgeMindMap', () => {
  it('loads the document-level mind map endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ document_id: 'doc-1', title: '资料', nodes: [] }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getKnowledgeMindMap('doc-1');

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/knowledge/doc-1/mindmap', undefined);
  });
});
