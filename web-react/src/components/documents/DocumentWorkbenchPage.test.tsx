import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useDocumentWorkbench } from '../../hooks/useDocumentWorkbench';
import DocumentWorkbenchPage from './DocumentWorkbenchPage';

vi.mock('../../hooks/useDocumentWorkbench');

const readyDocument = {
  id: 'a6b23452-1b5c-43af-a0b5-7cf5c29aa7ec', original_name: 'ready.md', suffix: '.md', media_type: 'text/markdown',
  size_bytes: 5, created_at: 1, extraction_status: 'ready' as const, text_truncated: false, sources: [],
};
const pendingDocument = { ...readyDocument, id: '9f2f7cd5-0f67-4db7-96a4-b7d1ac432817', original_name: 'pending.pdf', extraction_status: 'pending' as const };

describe('DocumentWorkbenchPage', () => {
  beforeEach(() => {
    vi.mocked(useDocumentWorkbench).mockReturnValue({
      documents: [readyDocument, pendingDocument], drafts: [], selectedIds: [], draft: null, template: 'prd', instructions: '',
      title: '', markdown: '', ready: true, busy: false, saveState: 'idle', error: '', mobilePane: 'library',
      setTemplate: vi.fn(), setInstructions: vi.fn(), setMobilePane: vi.fn(), toggleDocument: vi.fn(), upload: vi.fn(),
      remove: vi.fn(), generate: vi.fn(), openDraft: vi.fn(), setTitle: vi.fn(), setMarkdown: vi.fn(), save: vi.fn(), reloadDraft: vi.fn(),
    });
  });

  it('disables a pending document but allows a ready document to be selected', async () => {
    const user = userEvent.setup();
    render(<DocumentWorkbenchPage />);

    expect(screen.getByRole('checkbox', { name: /pending\.pdf/i })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /ready\.md/i }));

    expect(vi.mocked(useDocumentWorkbench).mock.results[0].value.toggleDocument).toHaveBeenCalledWith(readyDocument.id);
  });

  it('renders named mobile workspace tabs', () => {
    render(<DocumentWorkbenchPage />);
    expect(screen.getByRole('tab', { name: '资料' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '生成' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '编辑' })).toBeInTheDocument();
  });
});
