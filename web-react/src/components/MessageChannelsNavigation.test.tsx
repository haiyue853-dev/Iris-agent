import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import AppSidebar from './app-sidebar';

it('opens message channels from more tools', async () => {
  localStorage.clear();
  const onViewChange = vi.fn();
  render(
    <AppSidebar
      onNewChat={vi.fn()}
      currentSessionId=""
      sessions={[]}
      onSessionSwitch={vi.fn()}
      onSessionDelete={vi.fn()}
      activeView="chat"
      onViewChange={onViewChange}
    />,
  );

  await userEvent.click(screen.getByRole('button', { name: '更多工具' }));
  await userEvent.click(screen.getByRole('button', { name: '消息渠道' }));

  expect(onViewChange).toHaveBeenCalledWith('channels');
});
