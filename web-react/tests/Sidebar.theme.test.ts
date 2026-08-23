import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(resolve(process.cwd(), 'src', 'App.css'), 'utf8');

describe('AI daily report sidebar theme', () => {
  it('defines the compact responsive Iris sidebar', () => {
    expect(appCss).toContain('.iris-sidebar');
    expect(appCss).toContain(".iris-sidebar[data-collapsed='true']");
    expect(appCss).toContain('width: min(86vw, 300px)');
  });
  it('reuses the shared menu font and interaction states', () => {
    const sharedItemIndex = appCss.indexOf('.view-item {');
    const buttonResetIndex = appCss.indexOf('button.view-item {');
    const hoverIndex = appCss.indexOf('.view-item:hover');
    const activeIndex = appCss.indexOf('.view-item.active');

    expect(appCss).not.toMatch(/\.sidebar-view-nav\s+\.report-view-item\s*\{/);
    expect(buttonResetIndex).toBeGreaterThan(sharedItemIndex);
    expect(buttonResetIndex).toBeLessThan(hoverIndex);
    expect(buttonResetIndex).toBeLessThan(activeIndex);

    const buttonReset = appCss.slice(buttonResetIndex, appCss.indexOf('}', buttonResetIndex) + 1);
    expect(buttonReset).toContain('font-family: inherit;');
    expect(buttonReset).not.toContain('font: inherit;');
  });
});
