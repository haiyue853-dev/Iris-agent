import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SkillsPage from './SkillsPage';

const SKILLS = [
  {
    id: 'daily-report',
    name: 'AI 日报',
    description: '生成本地日报',
    icon: 'calendar',
    category: 'productivity',
    entry_view: 'reports',
    version: 1,
    enabled: true,
  },
  {
    id: 'uml',
    name: 'UML 流程图',
    description: '生成流程图',
    icon: 'diagram',
    category: 'development',
    entry_view: 'uml',
    version: 1,
    enabled: true,
  },
  {
    id: 'document-workbench',
    name: '文档工作台',
    description: '上传资料',
    icon: 'file-text',
    category: 'productivity',
    entry_view: 'documents',
    version: 1,
    enabled: false,
  },
  {
    id: 'hot-radar',
    name: '热点雷达',
    description: '热点订阅',
    icon: 'radar',
    category: 'news',
    entry_view: 'radar',
    version: 1,
    enabled: true,
  },
];

function response(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe('SkillsPage behavior', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('announces loading before the skills are available', () => {
    let resolveFetch!: (value: Response) => void;
    const pendingFetch = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pendingFetch));

    render(<SkillsPage onNavigate={vi.fn()} />);

    expect(screen.getByRole('status', { name: '正在加载 Skills' })).toBeInTheDocument();
    resolveFetch(response({ skills: SKILLS }));
  });

  it.each([
    ['AI 日报', 'reports'],
    ['UML 流程图', 'uml'],
    ['文档工作台', 'documents'],
    ['热点雷达', 'radar'],
  ])('opens %s from its accessible action', async (name, view) => {
    const enabledSkills = SKILLS.map((skill) =>
      skill.name === name ? { ...skill, enabled: true } : skill,
    );
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ skills: enabledSkills })));
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<SkillsPage onNavigate={onNavigate} />);

    await user.click(await screen.findByRole('button', { name: `打开 ${name}` }));

    expect(onNavigate).toHaveBeenCalledWith(view);
  });

  it('opens the focused action with the keyboard', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ skills: SKILLS })));
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<SkillsPage onNavigate={onNavigate} />);

    const openButton = await screen.findByRole('button', { name: '打开 AI 日报' });
    await user.tab();
    expect(openButton).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(onNavigate).toHaveBeenCalledWith('reports');
  });

  it('enables a disabled skill without opening it, then makes its open action available', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ skills: SKILLS }))
      .mockResolvedValueOnce(response({ ...SKILLS[2], enabled: true }));
    vi.stubGlobal('fetch', fetchMock);
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<SkillsPage onNavigate={onNavigate} />);

    const openButton = await screen.findByRole('button', { name: '打开 文档工作台' });
    expect(openButton).toBeDisabled();

    await user.click(screen.getByRole('button', { name: '启用 文档工作台' }));

    expect(onNavigate).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/skills/document-workbench/enabled'),
      expect.objectContaining({ method: 'PUT' }),
    );
    expect(await screen.findByRole('button', { name: '打开 文档工作台' })).toBeEnabled();
  });

  it('disables an enabled skill without opening it and sends the disabled state to the API', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ skills: SKILLS }))
      .mockResolvedValueOnce(response({ ...SKILLS[0], enabled: false }));
    vi.stubGlobal('fetch', fetchMock);
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<SkillsPage onNavigate={onNavigate} />);

    await user.click(await screen.findByRole('button', { name: '停用 AI 日报' }));

    expect(onNavigate).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/skills/daily-report/enabled'),
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ enabled: false }) }),
    );
    expect(await screen.findByRole('button', { name: '打开 AI 日报' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '启用 AI 日报' })).toBeInTheDocument();
  });

  it('shows a retry action after a loading error and loads cards when retried', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('服务暂时不可用'))
      .mockResolvedValueOnce(response({ skills: SKILLS }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<SkillsPage onNavigate={vi.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('服务暂时不可用');
    await user.click(screen.getByRole('button', { name: '重试加载 Skills' }));

    expect(await screen.findByRole('button', { name: '打开 AI 日报' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
