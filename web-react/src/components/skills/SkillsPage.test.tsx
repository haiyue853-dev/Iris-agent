import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SkillsPage from './SkillsPage';

const SKILLS = [
  { id: 'daily-report', name: 'AI 日报', description: '生成本地日报', icon: 'calendar', category: 'productivity', entry_view: 'reports', version: 1, enabled: true },
  { id: 'uml', name: 'UML 流程图', description: '生成流程图', icon: 'diagram', category: 'development', entry_view: 'uml', version: 1, enabled: true },
  { id: 'hot-radar', name: '热点雷达', description: '热点订阅', icon: 'radar', category: 'news', entry_view: 'radar', version: 1, enabled: false },
];

const USER_SKILL = {
  id: 'meeting-notes-a1b2c3', name: '我的 Skill', description: '整理会议记录', icon: 'sparkles',
  category: 'custom', entry_view: 'chat', version: 1, enabled: true, source: 'user',
};

function stubSkillsFetch(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => body })
  );
}

describe('SkillsPage', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it('shows bundled skill cards without document workbench', async () => {
    stubSkillsFetch({ skills: SKILLS });
    render(<SkillsPage onNavigate={vi.fn()} />);

    expect(await screen.findByText('AI 日报')).toBeInTheDocument();
    expect(screen.getByText('UML 流程图')).toBeInTheDocument();
    expect(screen.getByText('热点雷达')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^打开 / })).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: /^停用 / })).toHaveLength(2);
  });

  it('shows disabled state and allows enabling', async () => {
    stubSkillsFetch({ skills: SKILLS.map((skill) => skill.id === 'uml' ? { ...skill, enabled: true } : skill) });
    const user = userEvent.setup();
    render(<SkillsPage onNavigate={vi.fn()} />);

    await screen.findByText('热点雷达');
    expect(screen.getByText(/已停用/)).toBeInTheDocument();

    stubSkillsFetch({ ...SKILLS[2], enabled: true });
    await user.click(screen.getByRole('button', { name: '启用 热点雷达' }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/skills/hot-radar/enabled'),
        expect.objectContaining({ method: 'PUT' })
      )
    );
  });

  it('opens the target view when clicking an enabled card', async () => {
    stubSkillsFetch({ skills: SKILLS });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<SkillsPage onNavigate={onNavigate} />);

    await screen.findByText('UML 流程图');
    await user.click(screen.getByRole('button', { name: '打开 UML 流程图' }));
    expect(onNavigate).toHaveBeenCalledWith('uml');
  });

  it('does not navigate when clicking a disabled card', async () => {
    stubSkillsFetch({ skills: SKILLS });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<SkillsPage onNavigate={onNavigate} />);

    await screen.findByText('热点雷达');
    await user.click(screen.getByRole('button', { name: '打开 热点雷达' }));
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it('shows error state when loading fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('boom')));
    render(<SkillsPage onNavigate={vi.fn()} />);

    expect(await screen.findByText(/boom/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试加载 Skills' })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('saves a new custom Skill from the inline editor', async () => {
    const fetchMock = vi.fn().mockImplementation((_input: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify(USER_SKILL), { status: 201 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ skills: SKILLS }), { status: 200 }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<SkillsPage onNavigate={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: '新建 Skill' }));
    const dialog = await screen.findByRole('dialog', { name: '新建 Skill' });
    await user.type(within(dialog).getByLabelText('Skill 名称'), '会议整理');
    await user.type(within(dialog).getByLabelText('用途说明'), '整理会议记录');
    await user.type(within(dialog).getByLabelText('Skill 正文'), '输出行动项');
    await user.click(within(dialog).getByRole('button', { name: '保存 Skill' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/skills/user',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: '会议整理', description: '整理会议记录', content: '输出行动项', allowed_toolsets: [] }) }),
    ));
  });

  it('only shows edit and delete actions for a user Skill', async () => {
    stubSkillsFetch({ skills: [...SKILLS, USER_SKILL] });
    render(<SkillsPage onNavigate={vi.fn()} />);

    expect(await screen.findByRole('button', { name: '编辑 我的 Skill' })).toBeVisible();
    expect(screen.getByRole('button', { name: '删除 我的 Skill' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '编辑 AI 日报' })).toBeNull();
  });
});
