import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ToolsPage from './ToolsPage';

describe('ToolsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('shows the available tools returned by the API', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          tools: [
            { name: 'read_file', description: '读取工作区文件', requires_approval: false },
            { name: 'run_command', description: '执行命令', requires_approval: true },
          ],
        }),
        { status: 200 },
      ),
    );

    render(<ToolsPage />);

    expect(await screen.findByText('read_file')).toBeVisible();
    expect(screen.getByText('读取工作区文件')).toBeVisible();
    expect(screen.getByText('执行命令')).toBeVisible();
    expect(screen.getByText('需确认')).toBeVisible();
    expect(screen.getByText('直接可用')).toBeVisible();
  });
});
