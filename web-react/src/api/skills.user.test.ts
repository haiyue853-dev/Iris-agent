import { describe, expect, it, vi } from 'vitest';

import { saveUserSkill } from './skills';

describe('custom Skill API', () => {
  it('posts custom Skill fields and returns its metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 'meeting-notes-a1b2c3', name: '会议整理', description: '整理会议记录',
      icon: 'sparkles', category: 'custom', entry_view: 'chat', version: 1,
      enabled: true, source: 'user',
    }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    const skill = await saveUserSkill({ name: '会议整理', description: '整理会议记录', content: '整理输入', allowed_toolsets: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/skills/user',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: '会议整理', description: '整理会议记录', content: '整理输入', allowed_toolsets: [] }),
      }),
    );
    expect(skill.source).toBe('user');
    vi.unstubAllGlobals();
  });
});
