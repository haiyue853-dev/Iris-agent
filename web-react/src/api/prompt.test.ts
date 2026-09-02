import { afterEach, describe, expect, it, vi } from 'vitest';

import { optimizePrompt } from './prompt';

describe('prompt API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('returns the optimized prompt from the API response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ prompt: '优化后的提示词' }), { status: 200 })));

    await expect(optimizePrompt('原提示词')).resolves.toBe('优化后的提示词');
  });

  it('keeps the backend error message for visible feedback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { message: '请先配置可用模型' } }), { status: 503 })));

    await expect(optimizePrompt('原提示词')).rejects.toThrow('请先配置可用模型');
  });
});
