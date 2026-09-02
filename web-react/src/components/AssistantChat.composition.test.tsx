import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssistantChat } from './AssistantChat';
import { createSession, streamChat } from '../api/chat';
import { optimizePrompt } from '../api/prompt';
import { fetchSkills } from '../api/skills';

vi.mock('../api/chat', () => ({
  createSession: vi.fn(),
  streamChat: vi.fn(),
  streamToolApproval: vi.fn(),
}));

vi.mock('../api/prompt', () => ({ optimizePrompt: vi.fn() }));
vi.mock('../api/skills', () => ({ fetchSkills: vi.fn() }));
vi.mock('../api/settings', () => ({ fetchSettingsProfiles: vi.fn(async () => ({ profiles: [], active_id: null })) }));

if (typeof HTMLElement.prototype.scrollTo === 'undefined') {
  HTMLElement.prototype.scrollTo = () => {};
}

describe('AssistantChat composer', () => {
  beforeEach(() => {
    localStorage.clear();
  });

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
    expect(screen.getByRole('button', { name: '联网搜索' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '优化提示词' })).toBeVisible();
    expect(screen.getByRole('button', { name: '选择模型' })).toBeVisible();
  });

  it('selects one Skill as a visual chip without inserting its description into the draft', async () => {
    vi.mocked(fetchSkills).mockResolvedValue([
      { id: 'web-research', name: '网页研究', description: '抓取并整理完整网页内容', icon: 'sparkles', category: 'research', entry_view: 'chat', version: 1, enabled: true },
      { id: 'meeting-notes', name: '会议整理', description: '整理会议记录', icon: 'sparkles', category: 'custom', entry_view: 'chat', version: 1, enabled: true, source: 'user' },
    ]);
    render(<AssistantChat sessionId="" messages={[]} />);

    fireEvent.click(screen.getByRole('button', { name: '选择 Skill' }));
    await screen.findByRole('button', { name: '使用 Skill：网页研究' });
    fireEvent.click(screen.getByRole('button', { name: '使用 Skill：网页研究' }));

    await waitFor(() => expect(screen.getByLabelText('已激活 Skill：网页研究')).toBeVisible());
    expect(screen.getByRole('textbox', { name: '消息输入框' })).toHaveValue('');
    expect(screen.queryByText('抓取并整理完整网页内容')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '选择 Skill' }));
    await screen.findByRole('button', { name: '使用 Skill：会议整理' });
    fireEvent.click(screen.getByRole('button', { name: '使用 Skill：会议整理' }));
    await waitFor(() => expect(screen.getByLabelText('已激活 Skill：会议整理')).toBeVisible());
    expect(screen.queryByLabelText('已激活 Skill：网页研究')).not.toBeInTheDocument();
  });

  it('switches and persists the assistant capability mode for a new conversation', () => {
    localStorage.setItem('iris_chat_capability_mode', 'daily');
    render(<AssistantChat sessionId="" messages={[]} />);
    const mode = screen.getByRole('button', { name: '能力模式：日常' });
    fireEvent.click(mode);
    expect(localStorage.getItem('iris_chat_capability_mode')).toBe('research');
  });

  it('locks the capability mode after a session has started', () => {
    localStorage.setItem('iris_chat_capability_mode', 'daily');
    render(<AssistantChat sessionId="session-1" messages={[]} />);
    expect(screen.getByRole('button', { name: '能力模式：日常' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: '联网搜索' })).not.toBeDisabled();
  });

  it('enables online search for a new conversation', () => {
    render(<AssistantChat sessionId="" messages={[]} />);

    const online = screen.getByRole('button', { name: '联网搜索' });
    fireEvent.click(online);

    expect(online).toHaveAttribute('aria-pressed', 'true');
    expect(online).toHaveClass('is-online');
    expect(localStorage.getItem('iris_chat_online_search')).toBe('true');

    fireEvent.click(online);

    expect(online).toHaveAttribute('aria-pressed', 'false');
    expect(online).not.toHaveClass('is-online');
    expect(localStorage.getItem('iris_chat_online_search')).toBe('false');
  });

  it('fills the composer from a suggestion without submitting', () => {
    render(<AssistantChat sessionId="" messages={[]} />);
    fireEvent.click(screen.getByRole('button', { name: '分析这个项目' }));
    expect(screen.getByRole('textbox', { name: '消息输入框' })).toHaveValue('分析这个项目');
    expect(vi.mocked(createSession)).not.toHaveBeenCalled();
  });

  it('resends an edited message even when its text is unchanged', async () => {
    vi.mocked(streamChat).mockResolvedValueOnce();
    render(<AssistantChat sessionId="session-1" messages={[
      { id: 'message-1', role: 'user', content: '原始问题' },
    ]} />);

    fireEvent.click(await screen.findByRole('button', { name: '编辑消息' }));
    fireEvent.click(await screen.findByRole('button', { name: '更新并重发' }));

    await waitFor(() => expect(streamChat).toHaveBeenCalled());
    expect(vi.mocked(streamChat).mock.calls[0]?.slice(0, 2)).toEqual([
      'session-1',
      '原始问题',
    ]);
  });

  it('regenerates the backend turn and refreshes the session instead of adding a local branch', async () => {
    vi.mocked(streamChat).mockResolvedValueOnce();
    const onSessionRefreshed = vi.fn().mockResolvedValue([
      { id: 'user-1', role: 'user', content: '原始问题' },
      { id: 'assistant-2', role: 'assistant', content: '新回复' },
    ]);
    render(<AssistantChat
      sessionId="session-1"
      messages={[
        { id: 'user-1', role: 'user', content: '原始问题' },
        { id: 'assistant-1', role: 'assistant', content: '旧回复' },
      ]}
      onSessionRefreshed={onSessionRefreshed}
    />);

    fireEvent.click(await screen.findByRole('button', { name: '重新生成' }));

    await waitFor(() => expect(streamChat).toHaveBeenCalled());
    expect(vi.mocked(streamChat).mock.calls[0]?.[8]).toBe('user-1');
    await waitFor(() => expect(onSessionRefreshed).toHaveBeenCalledWith('session-1'));
  });

  it('replaces the draft with the optimized prompt without sending it', async () => {
    vi.mocked(optimizePrompt).mockResolvedValueOnce('优化后的会议邀请提示词');
    render(<AssistantChat sessionId="" messages={[]} />);
    const input = screen.getByRole('textbox', { name: '消息输入框' });
    fireEvent.change(input, { target: { value: '帮我写会议邀请' } });
    fireEvent.click(screen.getByRole('button', { name: '优化提示词' }));

    await waitFor(() => expect(screen.getByRole('textbox', { name: '消息输入框' })).toHaveValue('优化后的会议邀请提示词'));
    expect(screen.getByRole('status', { name: '提示词优化状态' })).toHaveTextContent('已优化提示词');
    expect(optimizePrompt).toHaveBeenCalledWith('帮我写会议邀请');
    expect(vi.mocked(createSession)).not.toHaveBeenCalled();
  });

  it('shows that prompt optimization is in progress', () => {
    vi.mocked(optimizePrompt).mockImplementationOnce(() => new Promise(() => {}));
    render(<AssistantChat sessionId="" messages={[]} />);
    const input = screen.getByRole('textbox', { name: '消息输入框' });
    fireEvent.change(input, { target: { value: '帮我写会议邀请' } });
    fireEvent.click(screen.getByRole('button', { name: '优化提示词' }));

    expect(screen.getByRole('status', { name: '提示词优化状态' })).toHaveTextContent('正在优化提示词');
  });

  it('explains when the optimized result does not change the draft', async () => {
    vi.mocked(optimizePrompt).mockResolvedValueOnce('帮我写会议邀请');
    render(<AssistantChat sessionId="" messages={[]} />);
    const input = screen.getByRole('textbox', { name: '消息输入框' });
    fireEvent.change(input, { target: { value: '帮我写会议邀请' } });
    fireEvent.click(screen.getByRole('button', { name: '优化提示词' }));

    await waitFor(() => expect(screen.getByRole('status', { name: '提示词优化状态' })).toHaveTextContent('原提示词已足够清晰'));
  });

  it('shows the optimization error without replacing the draft', async () => {
    vi.mocked(optimizePrompt).mockRejectedValueOnce(new Error('请先配置可用模型'));
    render(<AssistantChat sessionId="" messages={[]} />);
    const input = screen.getByRole('textbox', { name: '消息输入框' });
    fireEvent.change(input, { target: { value: '帮我写会议邀请' } });
    fireEvent.click(screen.getByRole('button', { name: '优化提示词' }));

    await waitFor(() => expect(screen.getByRole('status', { name: '提示词优化状态' })).toHaveTextContent('请先配置可用模型'));
    expect(input).toHaveValue('帮我写会议邀请');
  });
});
