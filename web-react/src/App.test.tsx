import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { useChat } from './hooks/useChat';

vi.mock('./hooks/useChat', () => ({
  useChat: vi.fn(),
}));

describe('App workspace navigation', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(useChat).mockReturnValue({
      messages: [],
      isStreaming: false,
      streamingContent: '',
      toast: '',
      pendingApproval: null,
      currentSessionId: '',
      sessions: [],
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
});
