import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import McpPage from './McpPage';

const server = {
  id: 'browser', name: 'Browser MCP', command: 'node', args: ['server.js'],
  allowed_tools: [], enabled: true, status: 'configured', discovered_tools: [],
};

function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe('McpPage', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('detects a connection through the discovery endpoint', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ servers: [server] }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response({ tools: [{ name: 'read_page', annotations: { readOnlyHint: true } }], server: { ...server, status: 'connected' } }))
      .mockResolvedValueOnce(response({ events: [] }));
    vi.stubGlobal('fetch', fetchMock);

    render(<McpPage />);
    expect(await screen.findByText('连接总览')).toBeInTheDocument();
    expect(screen.getByText('服务配置')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '检测连接' }));

    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/mcp/servers/browser/discover'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(await screen.findByText('read_page')).toBeInTheDocument();
    expect(screen.getByText('自动执行')).toBeInTheDocument();
    expect(screen.getByText('工具权限')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '选择全部可自动执行工具' }));
    expect(screen.getByRole('checkbox', { name: /read_page/ })).toBeChecked();
  });

  it('deletes only the selected MCP configuration', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ servers: [server] }))
      .mockResolvedValueOnce(response({ events: [] }))
      .mockResolvedValueOnce(response(null, 204))
      .mockResolvedValueOnce(response({ servers: [] }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('confirm', vi.fn(() => true));

    render(<McpPage />);
    fireEvent.click(await screen.findByRole('button', { name: '删除配置 Browser MCP' }));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/mcp/servers/browser'),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('shows safe recent connection status without tool arguments', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response({ servers: [server] }))
      .mockResolvedValueOnce(response({ events: [{ server_id: 'browser', kind: 'discovery', ok: true, duration_ms: 28, created_at: 1, arguments: { secret: true } }] })));

    render(<McpPage />);

    expect(await screen.findByText(/连接检测 · 成功/)).toBeInTheDocument();
    expect(screen.getByText('28ms')).toBeInTheDocument();
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });

  it('shows when authorized tools are available to the main conversation', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response({ servers: [{ ...server, allowed_tools: ['read_page'], discovered_tools: [{ name: 'read_page', annotations: { readOnlyHint: true } }] }] }))
      .mockResolvedValueOnce(response({ events: [] })));

    render(<McpPage />);

    expect(await screen.findByText('已接入主对话 · 1 个工具')).toBeInTheDocument();
  });
  it('identifies a persistent MCP session as connected', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response({ servers: [{ ...server, status: 'connected' }] }))
      .mockResolvedValueOnce(response({ events: [] })));

    render(<McpPage />);

    expect(await screen.findByTestId('mcp-session-state')).toHaveAttribute('data-status', 'connected');
  });
});
