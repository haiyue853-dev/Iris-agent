import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MessageChannelsPage from './MessageChannelsPage';

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
});

describe('MessageChannelsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      channels: [{
        id: 'qq',
        name: 'QQ',
        enabled: true,
        connected: true,
        transport: 'OneBot 11 反向 WebSocket',
        websocket_path: '/gateway/qq/ws',
      }],
    })));
  });

  it('shows the QQ connection state and reverse WebSocket address', async () => {
    render(<MessageChannelsPage />);

    expect(await screen.findByText('已连接')).toBeVisible();
    expect(screen.getByText('ws://localhost:8000/gateway/qq/ws')).toBeVisible();
    expect(screen.getByText('消息渠道')).toBeVisible();
    expect(screen.getByRole('region', { name: '消息渠道' })).toHaveClass('channel-page');
  });

  it('sends a test message to the entered QQ number', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(response({
        channels: [{ id: 'qq', name: 'QQ', enabled: true, connected: true, transport: 'OneBot 11 反向 WebSocket', websocket_path: '/gateway/qq/ws' }],
      }))
      .mockResolvedValueOnce(response({ ok: true }));

    render(<MessageChannelsPage />);
    await screen.findByText('已连接');
    await userEvent.type(screen.getByLabelText('测试 QQ 号'), '123456');
    await userEvent.click(screen.getByRole('button', { name: '发送测试消息' }));

    await waitFor(() => expect(screen.getByText('测试消息已发送')).toBeVisible());
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/gateway/qq/test',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('saves the NapCat path and starts NapCat', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(response({ channels: [{ id: 'qq', name: 'QQ', enabled: true, connected: false, transport: 'OneBot 11 反向 WebSocket', websocket_path: '/gateway/qq/ws' }] }))
      .mockResolvedValueOnce(response({ path: '', configured: false, running: false }))
      .mockResolvedValueOnce(response({ path: 'C:\\NapCat\\NapCat.Shell.exe', configured: true, running: false }))
      .mockResolvedValueOnce(response({ path: 'C:\\NapCat\\NapCat.Shell.exe', configured: true, running: true, already_running: false }));

    render(<MessageChannelsPage />);
    await screen.findByText('等待连接');
    const path = screen.getByLabelText('NapCat 可执行文件路径');
    await userEvent.type(path, 'C:\\NapCat\\NapCat.Shell.exe');
    await userEvent.click(screen.getByRole('button', { name: '保存路径' }));
    await waitFor(() => expect(screen.getByText('NapCat 路径已保存')).toBeVisible());
    await userEvent.click(screen.getByRole('button', { name: '打开 NapCat' }));
    await waitFor(() => expect(screen.getByText('NapCat 已启动')).toBeVisible());
    expect(fetchMock).toHaveBeenLastCalledWith('http://localhost:8000/api/gateway/napcat/open', expect.objectContaining({ method: 'POST' }));
  });

  it('matches a NapCat launcher from its folder', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(response({ channels: [{ id: 'qq', name: 'QQ', enabled: true, connected: false, transport: 'OneBot 11 反向 WebSocket', websocket_path: '/gateway/qq/ws' }] }))
      .mockResolvedValueOnce(response({ path: '', configured: false, running: false }))
      .mockResolvedValueOnce(response({ path: 'C:\\NapCat\\launcher.bat', configured: true, running: false }));

    render(<MessageChannelsPage />);
    await screen.findByText('等待连接');
    await userEvent.type(screen.getByLabelText('NapCat 文件夹路径'), 'C:\\NapCat');
    await userEvent.click(screen.getByRole('button', { name: '自动匹配' }));

    await waitFor(() => expect(screen.getByText('已匹配：launcher.bat')).toBeVisible());
    expect(fetchMock).toHaveBeenLastCalledWith('http://localhost:8000/api/gateway/napcat/match', expect.objectContaining({ method: 'POST' }));
  });
});
