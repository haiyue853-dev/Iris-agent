import type { ComponentProps } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReportWorkspace from './ReportWorkspace';

const rectFor = (width: number): DOMRect => ({
  x: 0,
  y: 0,
  top: 0,
  left: 0,
  right: width,
  bottom: 0,
  width,
  height: 0,
  toJSON: () => ({}),
});

const renderWorkspace = () => {
  const view = render(
    <ReportWorkspace
      activeMobilePane="history"
      onPaneChange={() => undefined}
      error=""
      history={<div>历史内容</div>}
      source={<div>助手内容</div>}
      preview={<div>预览内容</div>}
    />,
  );

  const history = view.container.querySelector('.report-pane.history') as HTMLDivElement;
  const source = view.container.querySelector('.report-pane.source') as HTMLDivElement;
  const preview = view.container.querySelector('.report-pane.preview') as HTMLDivElement;
  const workspace = view.container.querySelector('.report-workspace') as HTMLDivElement;
  Object.defineProperty(history, 'getBoundingClientRect', { value: () => rectFor(200) });
  Object.defineProperty(source, 'getBoundingClientRect', { value: () => rectFor(400) });
  Object.defineProperty(preview, 'getBoundingClientRect', { value: () => rectFor(400) });

  return { history, source, preview, workspace };
};

describe('ReportWorkspace', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('renders exactly two draggable separators for the three panes', () => {
    renderWorkspace();

    expect(screen.getAllByRole('separator')).toHaveLength(2);
  });

  it('scrolls the preview pane to top when a restore jump is requested', () => {
    type PropsWithPreviewJump = ComponentProps<typeof ReportWorkspace> & { previewJumpKey: number };
    const props = (previewJumpKey: number): PropsWithPreviewJump => ({
      activeMobilePane: 'history',
      onPaneChange: () => undefined,
      error: '',
      history: <div>历史内容</div>,
      source: <div>助手内容</div>,
      preview: <div>预览内容</div>,
      previewJumpKey,
    });
    const view = render(<ReportWorkspace {...props(0)} />);
    const preview = view.container.querySelector('.report-pane.preview') as HTMLDivElement;
    const scrollTo = vi.fn();
    Object.defineProperty(preview, 'scrollTo', { value: scrollTo });

    view.rerender(<ReportWorkspace {...props(1)} />);

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
  });

  it('resizes the adjacent desktop panes from the first divider', () => {
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(divider, { pointerId: 1, clientX: 250 });
    fireEvent.pointerUp(divider, { pointerId: 1 });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('250px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('350px');
  });

  it('resizes the assistant and preview panes from the second divider', () => {
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整助手与预览区域宽度' });
    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 600 });
    fireEvent.pointerMove(divider, { pointerId: 1, clientX: 630 });
    fireEvent.pointerUp(divider, { pointerId: 1 });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('200px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('430px');
  });

  it('keeps adjacent panes above their minimum widths while resizing', () => {
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(divider, { pointerId: 1, clientX: 0 });
    fireEvent.pointerUp(divider, { pointerId: 1 });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('180px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('420px');
  });

  it('keeps the preview pane above its minimum width while resizing', () => {
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整助手与预览区域宽度' });
    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 600 });
    fireEvent.pointerMove(divider, { pointerId: 1, clientX: 800 });
    fireEvent.pointerUp(divider, { pointerId: 1 });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('200px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('440px');
  });

  it('keeps the assistant pane above its minimum width from either divider', () => {
    const { workspace } = renderWorkspace();

    const firstDivider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    fireEvent.pointerDown(firstDivider, { pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(firstDivider, { pointerId: 1, clientX: 600 });
    fireEvent.pointerUp(firstDivider, { pointerId: 1 });
    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('320px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('280px');

    const secondDivider = screen.getByRole('separator', { name: '调整助手与预览区域宽度' });
    fireEvent.pointerDown(secondDivider, { pointerId: 2, clientX: 600 });
    fireEvent.pointerMove(secondDivider, { pointerId: 2, clientX: 0 });
    fireEvent.pointerUp(secondDivider, { pointerId: 2 });
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('280px');
  });

  it('supports keyboard resizing and clears the active divider after lost pointer capture', () => {
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    expect(divider.tabIndex).toBe(0);
    fireEvent.keyDown(divider, { key: 'ArrowRight' });
    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('224px');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('376px');

    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 200 });
    expect(divider).toHaveClass('active');
    fireEvent.lostPointerCapture(divider, { pointerId: 1 });
    expect(divider).not.toHaveClass('active');
  });

  it('announces the current keyboard resize range to assistive technology', () => {
    renderWorkspace();

    const divider = screen.getAllByRole('separator')[0];
    fireEvent.focus(divider);

    expect(divider).toHaveAttribute('aria-valuemin', '180');
    expect(divider).toHaveAttribute('aria-valuemax', '320');
    expect(divider).toHaveAttribute('aria-valuenow', '200');

    fireEvent.keyDown(divider, { key: 'ArrowRight' });
    expect(divider).toHaveAttribute('aria-valuenow', '224');
  });

  it('does not resize hidden dividers in the mobile tab layout', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
    const { workspace } = renderWorkspace();

    const divider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    fireEvent.pointerDown(divider, { pointerId: 1, clientX: 200 });
    fireEvent.pointerMove(divider, { pointerId: 1, clientX: 250 });
    fireEvent.keyDown(divider, { key: 'ArrowRight' });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('');
  });

  it('does not resize when the workspace is narrower than three desktop panes', () => {
    const { workspace } = renderWorkspace();
    Object.defineProperty(workspace, 'clientWidth', { value: 800 });

    const divider = screen.getByRole('separator', { name: '调整历史与助手区域宽度' });
    fireEvent.keyDown(divider, { key: 'ArrowRight' });

    expect(workspace.style.getPropertyValue('--report-history-width')).toBe('');
    expect(workspace.style.getPropertyValue('--report-source-width')).toBe('');
  });
});
