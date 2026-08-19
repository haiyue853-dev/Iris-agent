import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AttachmentChip from './AttachmentChip';

describe('AttachmentChip', () => {
  it('shows upload progress and an uploaded filename', () => {
    const { rerender } = render(<AttachmentChip attachment={{ client_id: 'local-1', original_name: 'notes.pdf', status: 'uploading' }} onRemove={vi.fn()} />);
    expect(screen.getByText('notes.pdf')).toBeInTheDocument();
    expect(screen.getByText('上传中')).toBeInTheDocument();

    rerender(<AttachmentChip attachment={{ client_id: 'local-1', id: 'attachment-1', original_name: 'notes.pdf', media_type: 'application/pdf', size_bytes: 32, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: ['第 1 页'], status: 'ready' }} onRemove={vi.fn()} />);
    expect(screen.getByText('已就绪')).toBeInTheDocument();
  });

  it('shows an upload error and lets the user remove it', () => {
    const onRemove = vi.fn();
    render(<AttachmentChip attachment={{ client_id: 'local-1', original_name: 'bad.exe', status: 'error', error: '不支持该附件' }} onRemove={onRemove} />);
    expect(screen.getByText('不支持该附件')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '移除 bad.exe' }));
    expect(onRemove).toHaveBeenCalledWith('local-1');
  });

  it('does not expose filesystem paths from upload errors', () => {
    render(<AttachmentChip attachment={{ client_id: 'local-1', original_name: 'bad.pdf', status: 'error', error: '无法保存 C:\\secret\\attachments\\bad.pdf' }} onRemove={vi.fn()} />);

    expect(screen.getByText('上传失败')).toBeInTheDocument();
    expect(screen.queryByText(/secret\\attachments/)).not.toBeInTheDocument();
  });
});
