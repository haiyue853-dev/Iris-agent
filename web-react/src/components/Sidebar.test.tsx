import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Sidebar from './Sidebar';

describe('Sidebar navigation', () => {
  it('switches from chat to the independent daily report view', async () => {
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

    await userEvent.click(screen.getByRole('button', { name: '日报' }));

    expect(onViewChange).toHaveBeenCalledWith('reports');
  });
});
