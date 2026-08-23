import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AssistantChat } from './AssistantChat';
import { createSession } from '../api/chat';

vi.mock('../api/chat', () => ({
  createSession: vi.fn(),
  streamChat: vi.fn(),
  streamToolApproval: vi.fn(),
}));

describe('AssistantChat composer', () => {
  it('keeps the visible draft while a Chinese IME composition is active', () => {
    render(<AssistantChat sessionId="" messages={[]} />);
    const input = screen.getByRole('textbox', { name: '消息输入框' });

    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: '中文' } });

    expect(input).toHaveValue('中文');
  });

  it('renders the AI Elements prompt structure and preview controls', () => {
    const { container } = render(<AssistantChat sessionId="" messages={[]} />);
    expect(container.querySelector('.iris-prompt-header')).toBeInTheDocument();
    expect(container.querySelector('.iris-prompt-body')).toBeInTheDocument();
    expect(container.querySelector('.iris-prompt-footer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '语音输入（暂未开放）' })).toBeVisible();
    expect(screen.getByRole('button', { name: '联网搜索（暂未开放）' })).toBeVisible();
    expect(screen.getByRole('button', { name: '选择模型（暂未开放）' })).toBeVisible();
  });

  it('fills the composer from a suggestion without submitting', () => {
    render(<AssistantChat sessionId="" messages={[]} />);
    fireEvent.click(screen.getByRole('button', { name: '分析这个项目' }));
    expect(screen.getByRole('textbox', { name: '消息输入框' })).toHaveValue('分析这个项目');
    expect(vi.mocked(createSession)).not.toHaveBeenCalled();
  });
});
