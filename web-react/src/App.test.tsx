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
      currentSessionId: '',
      sessions: [],
      handleSendWithSession: vi.fn(),
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
});

