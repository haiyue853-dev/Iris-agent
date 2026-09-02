import { describe, expect, it, vi } from 'vitest';

import { streamChat } from './chat';


describe('streamChat toolsets', () => {
  it('sends the selected toolsets in the chat request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await streamChat(
      'session-1', '分析项目', new AbortController().signal, vi.fn(),
      [], undefined, 'mix', false, undefined, 'fast', ['safe', 'research'],
    );

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.toolsets).toEqual(['safe', 'research']);
  });

  it('sends the selected Skill as metadata instead of changing the message', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await streamChat(
      'session-1', '用户原始问题', new AbortController().signal, vi.fn(),
      [], undefined, 'mix', false, undefined, 'fast', ['research'], 'web-research',
    );

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.message).toBe('用户原始问题');
    expect(body.skill_id).toBe('web-research');
  });
});
