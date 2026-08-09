import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(resolve(process.cwd(), 'src', 'App.css'), 'utf8');

function readRuleBody(source: string, selector: string) {
  const selectorIndex = source.indexOf(selector);
  const openingBraceIndex = source.indexOf('{', selectorIndex);
  const closingBraceIndex = source.indexOf('}', openingBraceIndex);
  if (selectorIndex < 0 || openingBraceIndex < 0 || closingBraceIndex < 0) {
    throw new Error(`Missing CSS rule: ${selector}`);
  }
  return source.slice(openingBraceIndex + 1, closingBraceIndex);
}

describe('AI daily report workspace dividers', () => {
  it('uses the two draggable separators as the only desktop pane boundaries', () => {
    const workspaceRule = readRuleBody(appCss, '.report-workspace');
    const paneRule = readRuleBody(appCss, '.report-pane');

    expect((workspaceRule.match(/\b8px\b/g) ?? [])).toHaveLength(2);
    expect(paneRule).not.toMatch(/border-right\s*:/);
    expect(appCss.match(/\.report-resizer::after/g) ?? []).toHaveLength(1);
  });
});
