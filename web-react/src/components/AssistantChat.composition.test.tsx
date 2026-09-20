import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssistantChat } from './AssistantChat';
import { createSession, streamChat } from '../api/chat';
import { optimizePrompt } from '../api/prompt';
import { fetchSkills } from '../api/skills';
import { uploadAttachment } from '../api/attachments';

vi.mock('../api/chat', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/chat')>(),
  createSession: vi.fn(),
  streamChat: vi.fn(),
  streamToolApproval: vi.fn(),
}));

vi.mock('../api/prompt', () => ({ optimizePrompt: vi.fn() }));
vi.mock('../api/skills', () => ({ fetchSkills: vi.fn() }));
vi.mock('../api/settings', () => ({ fetchSettingsProfiles: vi.fn(async () => ({ profiles: [], active_id: null })) }));
vi.mock('../api/attachments', () => ({
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
  attachmentDownloadUrl: vi.fn(() => 'http://localhost/attachment'),
}));

if (typeof HTMLElement.prototype.scrollTo === 'undefined') {
  HTMLElement.prototype.scrollTo = () => {};
}

describe('AssistantChat composer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('uploads dropped files and sends their backend attachment ids', async () => {
    vi.mocked(createSession).mockResolvedValue({ id: 'session-upload', name: 'notes.txt', created_at: 1, updated_at: 1 });
    vi.mocked(uploadAttachment).mockResolvedValue({
      id: 'attachment-1', original_name: 'notes.txt', media_type: 'text/plain', size_bytes: 4,
      created_at: '2026-09-20T00:00:00Z', extraction_status: 'ready', text_truncated: false, sources: [],
    });
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'message_completed', data: { message_id: 'assistant-upload', content: '已读取' } });
    });
    const { container } = render(<AssistantChat sessionId="" messages={[]} />);
    const dropzone = container.querySelector('.aui-composer-attachment-dropzone');
    const file = new File(['memo'], 'notes.txt', { type: 'text/plain' });

    fireEvent.drop(dropzone!, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledWith('session-upload', file));
    expect(await screen.findByText('notes.txt')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(streamChat).toHaveBeenCalled());
    expect(vi.mocked(streamChat).mock.calls[0]?.[4]).toEqual(['attachment-1']);
  });

  it('shows speech controls below completed assistant replies only', async () => {
    render(<AssistantChat sessionId="session-1" messages={[
      { id: 'user-1', role: 'user', content: '你好' },
      { id: 'assistant-1', role: 'assistant', content: '你好，我是高松灯。' },
    ]} />);

    expect(await screen.findAllByRole('button', { name: '语音朗读' })).toHaveLength(1);
  });

  it('hides speech controls for an empty assistant placeholder', async () => {
    render(<AssistantChat sessionId="session-1" messages={[
      { id: 'user-1', role: 'user', content: '你好' },
      { id: 'assistant-empty', role: 'assistant', content: '' },
    ]} />);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('button', { name: '语音朗读' })).not.toBeInTheDocument();
  });

  it('hides speech controls when an assistant reply contains only fenced code', async () => {
    render(<AssistantChat sessionId="session-1" messages={[
      { id: 'assistant-code', role: 'assistant', content: '```ts\nconst value = 1;\n```' },
    ]} />);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('button', { name: '语音朗读' })).not.toBeInTheDocument();
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

  it('keeps the composer free of preset example buttons', () => {
    render(<AssistantChat sessionId="" messages={[]} />);
    for (const name of ['分析这个项目', '帮我定位问题', '运行项目测试']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(screen.getByRole('textbox', { name: '消息输入框' })).toHaveValue('');
  });

  it('resends an edited message even when its text is unchanged', async () => {
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'message_completed', data: { content: '新回复' } });
    });
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
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'message_completed', data: { content: '新回复' } });
    });
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
    expect(vi.mocked(streamChat).mock.calls[0]?.[8]).toBe('assistant-1');
    await waitFor(() => expect(onSessionRefreshed).toHaveBeenCalledWith('session-1'));
  });

  it('regenerates the selected historical answer rather than the latest turn', async () => {
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'message_completed', data: { content: '第一答（新）' } });
    });
    const messages = [
      { id: 'user-1', role: 'user' as const, content: '第一问' },
      { id: 'assistant-1', role: 'assistant' as const, content: '第一答' },
      { id: 'user-2', role: 'user' as const, content: '第二问' },
      { id: 'assistant-2', role: 'assistant' as const, content: '第二答' },
    ];
    render(<AssistantChat sessionId="session-1" messages={messages} onSessionRefreshed={vi.fn().mockResolvedValue(messages)} />);

    const firstAnswer = (await screen.findByText('第一答')).closest('[data-role="assistant"]');
    fireEvent.mouseEnter(firstAnswer!);
    fireEvent.click(await within(firstAnswer as HTMLElement).findByRole('button', { name: '重新生成' }));

    await waitFor(() => expect(streamChat).toHaveBeenCalled());
    expect(vi.mocked(streamChat).mock.calls[0]?.[1]).toBe('第一问');
    expect(vi.mocked(streamChat).mock.calls[0]?.[8]).toBe('assistant-1');
  });

  it('shows an actionable model error when regeneration fails', async () => {
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'error', data: { code: 'provider_error', message: '模型服务调用失败' } });
    });
    const onSessionRefreshed = vi.fn().mockResolvedValue([
      { id: 'user-1', role: 'user', content: '原始问题' },
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
    expect(await screen.findByRole('alert')).toHaveTextContent('模型服务调用失败');
    expect(screen.getByRole('alert')).toHaveTextContent('API');
    expect(onSessionRefreshed).not.toHaveBeenCalled();
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
