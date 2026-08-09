import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';

import type { ReportPane } from '../../hooks/useDailyReports';

type Props = {
  activeMobilePane: ReportPane;
  onPaneChange: (pane: ReportPane) => void;
  error: string;
  previewJumpKey?: number;
  history: ReactNode;
  source: ReactNode;
  preview: ReactNode;
};

const panes: Array<[ReportPane, string]> = [
  ['history', '历史'],
  ['source', '助手'],
  ['preview', '预览'],
];

const minimumPaneWidths = [180, 280, 360] as const;
const dividerWidth = 8;
const minimumWorkspaceWidth = minimumPaneWidths.reduce(
  (total, width) => total + width,
  0,
) + dividerWidth * 2;
const keyboardResizeStep = 24;

type ResizeState = {
  dividerIndex: 0 | 1;
  pointerId: number;
  startX: number;
  widths: [number, number, number];
};

type PaneWidths = {
  history: number;
  source: number;
};

export default function ReportWorkspace({ activeMobilePane, onPaneChange, error, previewJumpKey = 0, history, source, preview }: Props) {
  const [paneWidths, setPaneWidths] = useState<PaneWidths | null>(null);
  const [accessiblePaneWidths, setAccessiblePaneWidths] = useState<[number, number, number] | null>(null);
  const [activeDivider, setActiveDivider] = useState<number | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<ResizeState | null>(null);

  useEffect(() => {
    if (previewJumpKey > 0) {
      previewRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [previewJumpKey]);

  const isMobileLayout = () => {
    const workspaceWidth = workspaceRef.current?.clientWidth ?? 0;

    return (
      window.matchMedia?.('(max-width: 960px)').matches === true ||
      (workspaceWidth > 0 && workspaceWidth <= minimumWorkspaceWidth)
    );
  };

  const readPaneWidths = (): [number, number, number] | null => {
    const widths = [historyRef, sourceRef, previewRef].map((ref) => ref.current?.getBoundingClientRect().width ?? 0);
    return widths.some((width) => width <= 0) ? null : widths as [number, number, number];
  };

  const updateAccessiblePaneWidths = () => {
    const widths = readPaneWidths();
    if (widths) setAccessiblePaneWidths(widths);
  };

  const dividerAria = (dividerIndex: 0 | 1) => {
    if (!accessiblePaneWidths) {
      return { 'aria-valuetext': '自动布局，按左右方向键调整宽度' };
    }

    const leftIndex = dividerIndex;
    const rightIndex = leftIndex + 1;
    return {
      'aria-valuemin': minimumPaneWidths[leftIndex],
      'aria-valuemax': Math.round(
        accessiblePaneWidths[leftIndex] + accessiblePaneWidths[rightIndex] - minimumPaneWidths[rightIndex],
      ),
      'aria-valuenow': Math.round(accessiblePaneWidths[leftIndex]),
    };
  };

  const resizePanes = (dividerIndex: 0 | 1, widths: [number, number, number], delta: number) => {
    const leftIndex = dividerIndex;
    const rightIndex = leftIndex + 1;
    const availableWidth = widths[leftIndex] + widths[rightIndex];
    const minLeft = minimumPaneWidths[leftIndex];
    const maxLeft = availableWidth - minimumPaneWidths[rightIndex];
    if (maxLeft < minLeft) return;

    const nextLeft = Math.min(Math.max(widths[leftIndex] + delta, minLeft), maxLeft);
    const nextWidths = [...widths] as [number, number, number];
    nextWidths[leftIndex] = nextLeft;
    nextWidths[rightIndex] = availableWidth - nextLeft;
    setAccessiblePaneWidths(nextWidths);
    setPaneWidths({ history: nextWidths[0], source: nextWidths[1] });
  };

  const startResize = (dividerIndex: 0 | 1, event: PointerEvent<HTMLDivElement>) => {
    if (resizeRef.current || isMobileLayout()) return;

    const widths = readPaneWidths();
    if (!widths) return;

    event.preventDefault();
    setAccessiblePaneWidths(widths);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    resizeRef.current = {
      dividerIndex,
      pointerId: event.pointerId,
      startX: event.clientX,
      widths: widths as [number, number, number],
    };
    setActiveDivider(dividerIndex);
  };

  const resize = (event: PointerEvent<HTMLDivElement>) => {
    const state = resizeRef.current;
    if (!state || state.pointerId !== event.pointerId) return;

    resizePanes(state.dividerIndex, state.widths, event.clientX - state.startX);
  };

  const stopResize = (event: PointerEvent<HTMLDivElement>) => {
    const state = resizeRef.current;
    if (!state || state.pointerId !== event.pointerId) return;

    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    resizeRef.current = null;
    setActiveDivider(null);
  };

  const resizeWithKeyboard = (dividerIndex: 0 | 1, event: KeyboardEvent<HTMLDivElement>) => {
    const delta = event.key === 'ArrowLeft' ? -keyboardResizeStep : event.key === 'ArrowRight' ? keyboardResizeStep : null;
    if (delta === null || isMobileLayout()) return;

    const widths = readPaneWidths();
    if (!widths) return;

    event.preventDefault();
    resizePanes(dividerIndex, widths, delta);
  };

  const workspaceStyle: CSSProperties | undefined = paneWidths
    ? {
        '--report-history-width': `${paneWidths.history}px`,
        '--report-source-width': `${paneWidths.source}px`,
      } as CSSProperties
    : undefined;

  return <>
    <div className="report-mobile-tabs" aria-label="日报页面区域">
      {panes.map(([pane, label]) => <button key={pane} className={activeMobilePane === pane ? 'active' : ''} onClick={() => onPaneChange(pane)}>{label}</button>)}
    </div>
    {error && <div className="report-error-banner" role="alert">{error}</div>}
    <div ref={workspaceRef} className="report-workspace" style={workspaceStyle}>
      <div ref={historyRef} className={`report-pane history ${activeMobilePane === 'history' ? 'active' : ''}`}>{history}</div>
      <div
        className={`report-resizer ${activeDivider === 0 ? 'active' : ''}`}
        role="separator"
        aria-label="调整历史与助手区域宽度"
        aria-orientation="vertical"
        {...dividerAria(0)}
        tabIndex={0}
        onPointerDown={(event) => startResize(0, event)}
        onPointerMove={resize}
        onPointerUp={stopResize}
        onPointerCancel={stopResize}
        onLostPointerCapture={stopResize}
        onFocus={updateAccessiblePaneWidths}
        onKeyDown={(event) => resizeWithKeyboard(0, event)}
      />
      <div ref={sourceRef} className={`report-pane source ${activeMobilePane === 'source' ? 'active' : ''}`}>{source}</div>
      <div
        className={`report-resizer ${activeDivider === 1 ? 'active' : ''}`}
        role="separator"
        aria-label="调整助手与预览区域宽度"
        aria-orientation="vertical"
        {...dividerAria(1)}
        tabIndex={0}
        onPointerDown={(event) => startResize(1, event)}
        onPointerMove={resize}
        onPointerUp={stopResize}
        onPointerCancel={stopResize}
        onLostPointerCapture={stopResize}
        onFocus={updateAccessiblePaneWidths}
        onKeyDown={(event) => resizeWithKeyboard(1, event)}
      />
      <div ref={previewRef} className={`report-pane preview ${activeMobilePane === 'preview' ? 'active' : ''}`}>{preview}</div>
    </div>
  </>;
}
