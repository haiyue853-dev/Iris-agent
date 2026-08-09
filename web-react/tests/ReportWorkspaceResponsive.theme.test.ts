import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(resolve(process.cwd(), 'src', 'App.css'), 'utf8');

function readAtRuleBody(source: string, atRule: string) {
  const atRuleIndex = source.indexOf(atRule);
  const openingBraceIndex = source.indexOf('{', atRuleIndex);
  if (atRuleIndex < 0 || openingBraceIndex < 0) {
    throw new Error(`Missing CSS at-rule: ${atRule}`);
  }

  let depth = 0;
  for (let index = openingBraceIndex; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) return source.slice(openingBraceIndex + 1, index);
  }

  throw new Error(`Unclosed CSS at-rule: ${atRule}`);
}

describe('AI daily report responsive workspace theme', () => {
  it('switches to tabs when the main content cannot fit all three panes', () => {
    const containerRule = readAtRuleBody(appCss, '@container (max-width: 836px)');

    expect(appCss).toMatch(/\.main-content\s*\{[^}]*container-type:\s*inline-size;/);
    expect(containerRule).toMatch(/\.report-mobile-tabs\s*\{[^}]*display:\s*grid;/);
    expect(containerRule).toMatch(/\.report-resizer\s*\{[^}]*display:\s*none;/);
  });
});
