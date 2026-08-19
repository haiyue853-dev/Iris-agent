import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import MessageBubble from './MessageBubble';

describe('MessageBubble attachment sources', () => {
  it('does not render absolute, UNC, or file URI source locations', () => {
    render(<MessageBubble role="assistant" content="已完成" onCopy={() => undefined} attachments={[{
      id: 'attachment-1', original_name: 'notes.pdf', media_type: 'application/pdf', size_bytes: 1, created_at: '2026-08-18T00:00:00Z', extraction_status: 'ready', text_truncated: false,
      sources: ['C:\\secret\\notes.pdf', '\\\\server\\share\\notes.pdf', 'file:///tmp/notes.pdf', '第 2 页'],
    }]} />);

    expect(screen.getAllByText((_, element) => element?.textContent === '来源：notes.pdf · 已定位')).toHaveLength(3);
    expect(screen.getByText('来源：notes.pdf · 第 2 页')).toBeInTheDocument();
    expect(screen.queryByText(/secret|server|file:\/\//)).not.toBeInTheDocument();
  });
});
