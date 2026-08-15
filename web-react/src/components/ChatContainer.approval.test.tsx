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
    render(<ChatContainer messages={[]} streamingContent="" isStreaming={false} inputValue="" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" onViewTask={onViewTask} />);

    fireEvent.click(screen.getByRole('button', { name: '查看任务' }));
    expect(onViewTask).toHaveBeenCalledWith('task-1');
  });

  it('shows queued and running task states without disabling follow-up messages', () => {
    render(<ChatContainer messages={[]} streamingContent="" isStreaming={true} inputValue="下一条" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" currentTaskStatus="queued" queuePosition={2} />);

    expect(screen.getByText('任务排队中（队列第 2 位）')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).not.toBeDisabled();
  });

  it('shows approval controls only when the awaiting task has an approval call id', () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const { rerender } = render(<ChatContainer messages={[]} streamingContent="" isStreaming={true} inputValue="" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" currentTaskStatus="awaiting_approval" onApproveTool={onApprove} onRejectTool={onReject} />);
    expect(screen.queryByRole('button', { name: '批准执行' })).not.toBeInTheDocument();

    rerender(<ChatContainer messages={[]} streamingContent="" isStreaming={true} inputValue="" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" currentTaskStatus="awaiting_approval" approvalCallId="call-1" onApproveTool={onApprove} onRejectTool={onReject} />);
    fireEvent.click(screen.getByRole('button', { name: '批准执行' }));
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));
    expect(onApprove).toHaveBeenCalledWith('call-1');
    expect(onReject).toHaveBeenCalledWith('call-1');
  });

  it('disables both task approval choices while one is submitting', () => {
    render(<ChatContainer messages={[]} streamingContent="" isStreaming={true} inputValue="" onInputChange={vi.fn()} onSend={vi.fn()} onStop={vi.fn()} onCopy={vi.fn()} onRegenerate={vi.fn()} onEdit={vi.fn()} currentTaskId="task-1" currentTaskStatus="awaiting_approval" approvalCallId="call-1" approvalSubmitting onApproveTool={vi.fn()} onRejectTool={vi.fn()} />);
    expect(screen.getByRole('button', { name: '批准执行' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '拒绝' })).toBeDisabled();
  });
});
