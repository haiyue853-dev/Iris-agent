import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ChatContainer from './ChatContainer';

describe('ChatContainer tool approval', () => {
  it('lets the user approve or reject a pending tool call', () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();

    render(<ChatContainer
      messages={[]}
      streamingContent=""
      reactSteps={[]}
      isStreaming={false}
      inputValue=""
      onInputChange={vi.fn()}
      onSend={vi.fn()}
      onStop={vi.fn()}
      onCopy={vi.fn()}
      onRegenerate={vi.fn()}
      onEdit={vi.fn()}
      pendingApproval={{ call_id: 'call-1', name: 'mcp__files__write_file', arguments: { path: 'a.txt' }, context: { server_name: 'Files', tool_name: 'write_file' } }}
      onApproveTool={onApprove}
      onRejectTool={onReject}
    />);

    expect(screen.getByText('需要确认工具操作')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '批准执行' }));
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));
    expect(onApprove).toHaveBeenCalledWith('call-1');
    expect(onReject).toHaveBeenCalledWith('call-1');
  });

  it('opens the current task from the chat workspace', () => {
    const onViewTask = vi.fn();
    render(<ChatContainer messages={[]} streamingContent="" reactSteps={[]} isStreaming={false} inputValue="" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" onViewTask={onViewTask} />);

    fireEvent.click(screen.getByRole('button', { name: '查看任务' }));
    expect(onViewTask).toHaveBeenCalledWith('task-1');
  });
});
