import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Sidebar from './Sidebar';

describe('Sidebar navigation', () => {
  it('switches from chat to the independent AI daily report view', async () => {
    const onViewChange = vi.fn();
    render(
      <Sidebar
        collapsed={false}
        onToggle={vi.fn()}
        onNewChat={vi.fn()}
        currentSessionId=""
        sessions={[]}
        onSessionSwitch={vi.fn()}
        onSessionDelete={vi.fn()}
        activeView="chat"
        onViewChange={onViewChange}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'AI 日报' }));

    expect(onViewChange).toHaveBeenCalledWith('reports');
  });

  it('returns to chat when selecting a conversation from the report view', async () => {
    const onViewChange = vi.fn();
    const onSessionSwitch = vi.fn();
    render(
      <Sidebar
        collapsed={false}
        onToggle={vi.fn()}
        onNewChat={vi.fn()}
        currentSessionId=""
        sessions={[{ id: 'session_1', name: '日报来源', created_at: 1, updated_at: 1 }]}
        onSessionSwitch={onSessionSwitch}
        onSessionDelete={vi.fn()}
        activeView="reports"
        onViewChange={onViewChange}
      />,
    );

    await userEvent.click(screen.getByText('日报来源'));

    expect(onSessionSwitch).toHaveBeenCalledWith('session_1');
    expect(onViewChange).toHaveBeenCalledWith('chat');
  });

  it('opens Skills from the single left-sidebar entry', async () => {
    const onViewChange = vi.fn();
    render(
      <Sidebar
        collapsed={false}
        onToggle={vi.fn()}
        onNewChat={vi.fn()}
        currentSessionId=""
        sessions={[]}
        onSessionSwitch={vi.fn()}
        onSessionDelete={vi.fn()}
        activeView="chat"
        onViewChange={onViewChange}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Skills' }));

    expect(onViewChange).toHaveBeenCalledWith('skills');
  });

  it('replaces document workbench with automation tasks', async () => {
    const onViewChange = vi.fn();
    render(<Sidebar collapsed={false} onToggle={vi.fn()} onNewChat={vi.fn()} currentSessionId="" sessions={[]} onSessionSwitch={vi.fn()} onSessionDelete={vi.fn()} activeView="chat" onViewChange={onViewChange} />);

    expect(screen.queryByText('文档工作台')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '自动化任务' }));
    expect(onViewChange).toHaveBeenCalledWith('automation');
  });
});
