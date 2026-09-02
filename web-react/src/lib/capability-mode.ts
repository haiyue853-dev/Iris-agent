export type Toolset = 'safe' | 'research' | 'coding' | 'knowledge' | 'skills' | 'delegation';
export type CapabilityMode = 'daily' | 'research' | 'collaboration';

export const CAPABILITY_MODE_KEY = 'iris_chat_capability_mode';
export const ONLINE_SEARCH_KEY = 'iris_chat_online_search';

export const CAPABILITY_MODE_LABELS: Record<CapabilityMode, string> = {
  daily: '日常',
  research: '研究',
  collaboration: '协作',
};

const TOOLSETS: Record<CapabilityMode, Toolset[]> = {
  daily: ['safe', 'skills'],
  research: ['safe', 'knowledge', 'skills'],
  collaboration: ['safe', 'knowledge', 'skills', 'delegation'],
};

export function readCapabilityMode(): CapabilityMode {
  const stored = localStorage.getItem(CAPABILITY_MODE_KEY);
  return stored === 'research' || stored === 'collaboration' ? stored : 'daily';
}

export function nextCapabilityMode(mode: CapabilityMode): CapabilityMode {
  if (mode === 'daily') return 'research';
  if (mode === 'research') return 'collaboration';
  return 'daily';
}

export function readOnlineSearchEnabled(): boolean {
  return localStorage.getItem(ONLINE_SEARCH_KEY) === 'true';
}

export function setOnlineSearchEnabled(enabled: boolean): void {
  localStorage.setItem(ONLINE_SEARCH_KEY, String(enabled));
}

export function withOnlineSearch(toolsets: Toolset[], enabled = readOnlineSearchEnabled()): Toolset[] {
  const withoutResearch = toolsets.filter((toolset) => toolset !== 'research');
  return enabled ? [...withoutResearch, 'research'] : withoutResearch;
}

export function toolsetsForMode(mode: CapabilityMode, online = readOnlineSearchEnabled()): Toolset[] {
  return withOnlineSearch(TOOLSETS[mode], online);
}
