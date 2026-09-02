import { describe, expect, it } from 'vitest';

import { toolsetsForMode } from './capability-mode';

describe('toolsetsForMode', () => {
  it('only adds online search tools when the online switch is enabled', () => {
    expect(toolsetsForMode('daily', false)).not.toContain('research');
    expect(toolsetsForMode('research', false)).not.toContain('research');
    expect(toolsetsForMode('collaboration', false)).not.toContain('research');
    expect(toolsetsForMode('daily', true)).toContain('research');
  });
});
