import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import userEvent from '@testing-library/user-event';
import { createSession, getSession, streamChat } from './api/chat';

vi.mock('./components/app-sidebar', () => ({ default: () => null }));
vi.mock('./api/chat', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api/chat')>(),
  listSessions: vi.fn(async () => []),
  createSession: vi.fn(),
  getSession: vi.fn(),
  streamChat: vi.fn(),
}));
vi.mock('./api/knowledge', async (importOriginal) => ({
  ...await importOriginal<typeof import('./api/knowledge')>(),
  listKnowledgeCollections: vi.fn(async () => []),
}));
vi.mock('./api/settings', () => ({ fetchSettingsProfiles: vi.fn(async () => ({ profiles: [], active_id: null })) }));

if (!HTMLElement.prototype.scrollTo) HTMLElement.prototype.scrollTo = () => {};

describe('chat failure feedback across session refresh', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(createSession).mockResolvedValue({ id: 'failed-session', name: '测试连接', created_at: 0, updated_at: 0 });
    vi.mocked(getSession).mockResolvedValue({ messages: [{ id: 'user-1', role: 'user', content: '测试连接' }] });
  });

  it('explains a connection failure before a session can be created', async () => {
    vi.mocked(createSession).mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByRole('textbox', { name: '消息输入框' }), '测试连接');
    await user.click(screen.getByRole('button', { name: '发送消息' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('无法连接 Iris 服务');
    expect(screen.getByRole('alert')).toHaveTextContent('后端已启动');
    expect(getSession).not.toHaveBeenCalled();
  });

  it('keeps the model failure visible after the new session history is loaded', async () => {
    vi.mocked(streamChat).mockImplementationOnce(async (_id, _text, _signal, onEvent) => {
      onEvent({ type: 'error', data: { code: 'provider_error', message: '模型服务调用失败' } });
    });
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByRole('textbox', { name: '消息输入框' }), '测试连接');
    await user.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(getSession).toHaveBeenCalledWith('failed-session'));
    await waitFor(() => expect(screen.queryByLabelText('思考中')).not.toBeInTheDocument());
    expect(screen.getAllByText(/模型服务调用失败/).length).toBeGreaterThan(0);
  });
});
