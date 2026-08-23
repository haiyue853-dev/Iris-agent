import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { useChat } from './hooks/useChat';

const assistantChatProps = vi.hoisted(() => [] as Array<{ onSessionCreated?: (id: string) => void }>);

vi.mock('./hooks/useChat', () => ({
  useChat: vi.fn(),
}));

vi.mock('./components/AssistantChat', () => ({
  AssistantChat: (props: { onSessionCreated?: (id: string) => void }) => {
    assistantChatProps.push(props);
    return <div data-testid="assistant-chat" />;
  },
}));

describe('App workspace navigation', () => {
  beforeEach(() => {
    assistantChatProps.length = 0;
    localStorage.clear();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
    vi.mocked(useChat).mockReturnValue({
      messages: [],
      isStreaming: false,
      streamingContent: '',
      toast: '',
      pendingApproval: null,
      currentSessionId: '',
      currentTaskId: null,
      currentTaskStatus: null,
      queuePosition: null,
      approvalCallId: null,
      approvalSubmitting: false,
      sessions: [],
      attachments: [],
      uploadFiles: vi.fn(),
      removeAttachment: vi.fn(),
      handleSendWithSession: vi.fn(),
      resolvePendingApproval: vi.fn(),
      handleRegenerate: vi.fn(),
      handleStop: vi.fn(),
      handleNewChat: vi.fn(),
      handleCopy: vi.fn(),
      handleEditMessage: vi.fn(),
      handleSwitchSession: vi.fn(),
      handleDeleteSession: vi.fn(),
    });
  });

  it('starts with the sidebar collapsed on narrow screens', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });

    render(<App />);

    expect(screen.getByTitle('展开侧边栏')).toBeInTheDocument();
    expect(document.querySelector('.sidebar')).toHaveClass('collapsed');
  });

  it('renders the AI Elements inspired application shell', () => {
    render(<App />);
    expect(document.querySelector('.iris-app-shell')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveClass('iris-main-surface');
  });

  it('opens the AI daily report workspace from the left sidebar', async () => {
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole('button', { name: 'AI 日报' }));

    expect(screen.getByRole('main', { name: 'AI 日报工作台' })).toBeInTheDocument();
    expect(localStorage.getItem('iris_active_view')).toBe('reports');
  });

  it('opens the Skills center from the left sidebar', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ skills: [] }) }));

    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Skills' }));

    expect(screen.getByRole('main', { name: 'Skills 中心' })).toBeInTheDocument();
    expect(localStorage.getItem('iris_active_view')).toBe('skills');
    vi.unstubAllGlobals();
  });

  it('opens automation tasks from the left sidebar', async () => {
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole('button', { name: '自动化任务' }));

    expect(screen.getByRole('main', { name: '自动化任务' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '自动化任务' })).toBeInTheDocument();
    expect(localStorage.getItem('iris_active_view')).toBe('automation');
  });

  it('restores the Skills center selected in local storage', async () => {
    localStorage.setItem('iris_active_view', 'skills');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ skills: [] }) }));

    render(<App />);

    expect(screen.getByRole('main', { name: 'Skills 中心' })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('keeps the session-created callback stable across parent rerenders', () => {
    const { rerender } = render(<App />);
    const firstCallback = assistantChatProps.at(-1)?.onSessionCreated;

    rerender(<App />);

    expect(firstCallback).toBeDefined();
    expect(assistantChatProps.at(-1)?.onSessionCreated).toBe(firstCallback);
  });

});
