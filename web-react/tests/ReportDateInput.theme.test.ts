import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(resolve(process.cwd(), 'src', 'App.css'), 'utf8');

describe('AI daily report date input theme', () => {
  it('keeps the native date controls usable inside a compact field', () => {
    expect(appCss).toMatch(/\.report-source-editor \.report-field > input\[type='date'\]\s*\{[^}]*height:\s*34px;[^}]*padding:\s*6px 10px;/);
    expect(appCss).not.toContain('::-webkit-inner-spin-button');
    expect(appCss).not.toContain('::-webkit-calendar-picker-indicator');
  });
});
