import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import InputBox from './InputBox';

describe('InputBox attachments', () => {
  it('shows selected files and prevents sending while an upload is pending', () => {
    const onSend = vi.fn();
    render(<InputBox value="请分析" onChange={vi.fn()} onSend={onSend} attachments={[{ client_id: 'local-1', original_name: 'notes.txt', status: 'uploading' }]} onFilesSelected={vi.fn()} onRemoveAttachment={vi.fn()} />);

    expect(screen.getByText('notes.txt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
  });

  it('sends ready attachment ids and exposes a file selector', () => {
    const onSend = vi.fn();
    const onFilesSelected = vi.fn();
    render(<InputBox value="请分析" onChange={vi.fn()} onSend={onSend} attachments={[{ client_id: 'local-1', id: 'attachment-1', original_name: 'notes.txt', media_type: 'text/plain', size_bytes: 4, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: [], status: 'ready' }]} onFilesSelected={onFilesSelected} onRemoveAttachment={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(onSend).toHaveBeenCalledWith('请分析', ['attachment-1']);

    fireEvent.change(screen.getByLabelText('添加附件'), { target: { files: [new File(['memo'], 'memo.txt', { type: 'text/plain' })] } });
    expect(onFilesSelected).toHaveBeenCalledWith([expect.any(File)]);
  });
});
