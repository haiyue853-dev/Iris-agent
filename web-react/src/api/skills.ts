import type { SkillInfo } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 获取全部内置 Skill */
export async function fetchSkills(): Promise<SkillInfo[]> {
  const response = await checked(await fetch(`${API_BASE}/api/skills`));
  const data = await response.json();
  return (data.skills ?? []) as SkillInfo[];
}

/** 切换 Skill 启用状态 */
export async function setSkillEnabled(id: string, enabled: boolean): Promise<SkillInfo> {
  const response = await checked(
    await fetch(`${API_BASE}/api/skills/${encodeURIComponent(id)}/enabled`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
  );
  return (await response.json()) as SkillInfo;
}
