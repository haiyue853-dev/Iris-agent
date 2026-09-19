import { describe, expect, it } from 'vitest';

import { toolsetsForMode } from './capability-mode';

describe('toolsetsForMode', () => {
  it('only adds online search tools when the online switch is enabled', () => {
    expect(toolsetsForMode('daily', false)).not.toContain('research');
    expect(toolsetsForMode('research', false)).not.toContain('research');
    expect(toolsetsForMode('collaboration', false)).not.toContain('research');
    expect(toolsetsForMode('daily', true)).toContain('research');
  });

  it('keeps enabled MCP tools available in every chat capability mode', () => {
    expect(toolsetsForMode('daily', false)).toContain('mcp');
    expect(toolsetsForMode('research', false)).toContain('mcp');
    expect(toolsetsForMode('collaboration', true)).toContain('mcp');
  });
});
