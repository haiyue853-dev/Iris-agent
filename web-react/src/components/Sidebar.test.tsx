import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AppSidebar from './app-sidebar';

describe('AppSidebar navigation', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const renderSidebar = (overrides: Partial<React.ComponentProps<typeof AppSidebar>> = {}) =>
    render(
      <AppSidebar
        onNewChat={vi.fn()}
        currentSessionId=""
        sessions={[]}
        onSessionSwitch={vi.fn()}
        onSessionDelete={vi.fn()}
        activeView="chat"
        onViewChange={vi.fn()}
        {...overrides}
      />,
    );

  it('keeps all navigation regions in the expanded sidebar', () => {
    renderSidebar({ sessions: [{ id: 's1', name: '设计讨论', created_at: 1, updated_at: 1 }] });
    expect(screen.getByText('Iris')).toBeVisible();
    expect(screen.getByRole('button', { name: /新建会话/ })).toBeVisible();
    expect(screen.getByRole('navigation', { name: '功能导航' })).toBeVisible();
    expect(screen.getByRole('navigation', { name: '历史对话' })).toBeVisible();
    expect(screen.getByRole('button', { name: '设置' })).toBeVisible();
  });

  it('exposes expanded state on the sidebar shell by default', () => {
    const { container } = renderSidebar();
    const shell = container.querySelector('[data-slot="sidebar"]');
    expect(shell).toHaveAttribute('data-state', 'expanded');
  });

  it('toggles expanded/collapsed when the trigger is clicked', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();
    const shell = container.querySelector('[data-slot="sidebar"]');
    expect(shell).toHaveAttribute('data-state', 'expanded');

    await user.click(screen.getByRole('button', { name: 'Toggle Sidebar' }));
    expect(shell).toHaveAttribute('data-state', 'collapsed');
  });

  it('toggles via Ctrl/Cmd + B keyboard shortcut', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();
    const shell = container.querySelector('[data-slot="sidebar"]');

    await user.keyboard('{Control>}b{/Control}');
    expect(shell).toHaveAttribute('data-state', 'collapsed');

    await user.keyboard('{Control>}b{/Control}');
    expect(shell).toHaveAttribute('data-state', 'expanded');
  });

  it('switches from chat to the independent AI daily report view', async () => {
    const onViewChange = vi.fn();
    renderSidebar({ onViewChange });

    await userEvent.click(screen.getByRole('button', { name: 'AI 日报' }));

    expect(onViewChange).toHaveBeenCalledWith('reports');
  });

  it('returns to chat when selecting a conversation from the report view', async () => {
    const onViewChange = vi.fn();
    const onSessionSwitch = vi.fn();
    render(
      <AppSidebar
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
    renderSidebar({ onViewChange });

    await userEvent.click(screen.getByRole('button', { name: 'Skills' }));

    expect(onViewChange).toHaveBeenCalledWith('skills');
  });

  it('opens the available tools page from the left sidebar', async () => {
    const onViewChange = vi.fn();
    renderSidebar({ onViewChange });

    await userEvent.click(screen.getByRole('button', { name: '更多工具' }));
    await userEvent.click(screen.getByRole('button', { name: '工具' }));

    expect(onViewChange).toHaveBeenCalledWith('tools');
  });

  it('uses a distinct icon for Skills instead of the home icon', () => {
    const { container } = renderSidebar();
    const skillsIcon = screen.getByRole('button', { name: 'Skills' }).querySelector('svg');
    const homeIcon = container.querySelector('[data-slot="sidebar-home"] svg');

    expect(skillsIcon).toBeInTheDocument();
    expect(homeIcon).toBeInTheDocument();
    expect(skillsIcon?.innerHTML).not.toBe(homeIcon?.innerHTML);
  });
  it('opens the task center from the left sidebar', async () => {
    const onViewChange = vi.fn();
    renderSidebar({ onViewChange });

    await userEvent.click(screen.getByRole('button', { name: '更多工具' }));
    await userEvent.click(screen.getByRole('button', { name: '任务中心' }));

    expect(onViewChange).toHaveBeenCalledWith('tasks');
  });

  it('collapses secondary tools by default and remembers expansion', async () => {
    const user = userEvent.setup();
    const first = renderSidebar();

    expect(screen.queryByRole('button', { name: '记忆' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '更多工具' }));
    expect(screen.getByRole('button', { name: '记忆' })).toBeVisible();
    expect(localStorage.getItem('iris_more_tools_expanded')).toBe('true');

    first.unmount();
    renderSidebar();
    expect(screen.getByRole('button', { name: '记忆' })).toBeVisible();
  });

  it('replaces document workbench with automation tasks', async () => {
    const onViewChange = vi.fn();
    renderSidebar({ onViewChange });

    expect(screen.queryByText('文档工作台')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '自动化任务' }));
    expect(onViewChange).toHaveBeenCalledWith('automation');
  });

  it('hides labels and shows tooltip when collapsed', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();
    await user.click(screen.getByRole('button', { name: 'Toggle Sidebar' }));
    const shell = container.querySelector('[data-slot="sidebar"]');
    expect(shell).toHaveAttribute('data-state', 'collapsed');
    // 折叠后 "新建会话" 文字应被 CSS 隐藏 (data-state 切换)
    const label = screen.getByText('新建会话');
    expect(label).toBeInTheDocument();
  });

  it('keeps menu icons visible after collapsing the sidebar', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();
    await user.click(screen.getByRole('button', { name: 'Toggle Sidebar' }));
    const shell = container.querySelector('[data-slot="sidebar"]');
    expect(shell).toHaveAttribute('data-state', 'collapsed');
    // 折叠后,菜单按钮内的 .sidebar-icon SVG 应仍存在 (CSS 仅隐藏 .sidebar-label 等文字)
    const menuButton = container.querySelector('[data-slot="sidebar-menu-button"]');
    const icon = menuButton?.querySelector('.sidebar-icon');
    expect(icon).toBeInTheDocument();
  });

  it('exposes a clickable home button in the header that returns to chat', async () => {
    const onViewChange = vi.fn();
    renderSidebar({ activeView: 'reports', onViewChange });
    const home = screen.getByRole('button', { name: '返回首页' });
    expect(home).toBeInTheDocument();
    await userEvent.click(home);
    expect(onViewChange).toHaveBeenCalledWith('chat');
  });

  it('marks the home button as active when on the chat view', () => {
    const { container } = renderSidebar({ activeView: 'chat' });
    const home = container.querySelector('[data-slot="sidebar-home"]');
    expect(home).toHaveAttribute('data-active', 'true');
  });

  it('does not apply flex-1 to the home button (regression: would shrink to 2px in 56px sidebar)', () => {
    const { container } = renderSidebar();
    const home = container.querySelector('[data-slot="sidebar-home"]');
    expect(home?.className).not.toMatch(/flex-1/);
    expect(home?.className).toMatch(/shrink-0/);
  });

  it('keeps home and rail button in DOM when collapsed', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();
    await user.click(screen.getByRole('button', { name: 'Toggle Sidebar' }));
    expect(container.querySelector('[data-slot="sidebar-home"]')).toBeInTheDocument();
    expect(container.querySelector('[data-slot="sidebar-rail"]')).toBeInTheDocument();
  });
});
