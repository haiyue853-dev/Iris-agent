import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DrawioEditor from './DrawioEditor';
import { DRAWIO_STORAGE_KEY } from './drawioStorage';

const DRAWIO_ORIGIN = 'https://embed.diagrams.net';
const originalCreateObjectUrl = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
const originalRevokeObjectUrl = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');

type FrameMessenger = {
  frame: HTMLIFrameElement;
  postMessage: ReturnType<typeof vi.fn>;
};

function mountEditor(props: Partial<ComponentProps<typeof DrawioEditor>> = {}): FrameMessenger {
  render(<DrawioEditor mermaidCode={'flowchart TD\n  A[Start] --> B[End]'} {...props} />);
  const frame = screen.getByTitle('Iris Draw.io 专业流程图') as HTMLIFrameElement;
  const postMessage = vi.fn();
  Object.defineProperty(frame.contentWindow, 'postMessage', { configurable: true, value: postMessage });
  return { frame, postMessage };
}

function sendMessage(frame: HTMLIFrameElement, origin: string, data: unknown, source: MessageEventSource | null = frame.contentWindow) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        data: typeof data === 'string' ? data : JSON.stringify(data),
        origin,
        source,
      })
    );
  });
}

describe('DrawioEditor', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:iris-export') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalCreateObjectUrl) Object.defineProperty(URL, 'createObjectURL', originalCreateObjectUrl);
    else Reflect.deleteProperty(URL, 'createObjectURL');
    if (originalRevokeObjectUrl) Object.defineProperty(URL, 'revokeObjectURL', originalRevokeObjectUrl);
    else Reflect.deleteProperty(URL, 'revokeObjectURL');
  });

  it('loads the saved diagram only after a trusted init message', () => {
    localStorage.setItem(DRAWIO_STORAGE_KEY, JSON.stringify({ version: 1, xml: '<mxfile />', updatedAt: 1 }));
    const { frame, postMessage } = mountEditor();

    sendMessage(frame, 'https://untrusted.example', { event: 'init' });
    sendMessage(frame, DRAWIO_ORIGIN, '{not json');
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' }, window);
    expect(postMessage).not.toHaveBeenCalled();

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });
    expect(postMessage).toHaveBeenCalledWith(
      expect.stringContaining('"action":"load"'),
      DRAWIO_ORIGIN
    );
    expect(postMessage).toHaveBeenCalledWith(
      expect.stringContaining('"xml":"<mxfile />"'),
      DRAWIO_ORIGIN
    );
  });

  it('stores trusted autosave and save XML in its own debounced storage record', () => {
    const { frame, postMessage } = mountEditor();

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'autosave', xml: '<mxfile id="autosave" />' });
    act(() => vi.advanceTimersByTime(399));
    expect(localStorage.getItem(DRAWIO_STORAGE_KEY)).toBeNull();

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'save', xml: '<mxfile id="save" />' });
    act(() => vi.advanceTimersByTime(401));

    expect(JSON.parse(localStorage.getItem(DRAWIO_STORAGE_KEY) || '{}')).toMatchObject({
      version: 1,
      xml: '<mxfile id="save" />',
    });
    expect(postMessage).toHaveBeenCalledWith(
      JSON.stringify({ action: 'status', modified: false }),
      DRAWIO_ORIGIN
    );
  });

  it('reports diagram presence as soon as a trusted autosave arrives, before its debounce is persisted', () => {
    const onDiagramPresenceChange = vi.fn();
    const { frame } = mountEditor({ onDiagramPresenceChange });

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'autosave', xml: '<mxfile id="dirty" />' });

    expect(onDiagramPresenceChange).toHaveBeenCalledWith(true);
    expect(localStorage.getItem(DRAWIO_STORAGE_KEY)).toBeNull();
  });

  it('imports Mermaid only when explicitly requested and uses the supported descriptor payload', () => {
    const { frame, postMessage } = mountEditor({ importRequest: 1 });

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });

    expect(postMessage).toHaveBeenCalledWith(
      JSON.stringify({
        action: 'load',
        descriptor: { format: 'mermaid', data: 'flowchart TD\n  A[Start] --> B[End]', wrap: true },
        sourceMetadata: { key: 'mermaidSource', value: 'flowchart TD\n  A[Start] --> B[End]' },
        autosave: 1,
        fit: 1,
      }),
      DRAWIO_ORIGIN
    );
  });

  it('notifies the parent when a Mermaid import request is consumed so a remounted frame cannot replay it', () => {
    const onImportConsumed = vi.fn();
    const first = render(<DrawioEditor mermaidCode="flowchart TD" importRequest={9} onImportConsumed={onImportConsumed} />);
    const firstFrame = screen.getByTitle('Iris Draw.io 专业流程图') as HTMLIFrameElement;
    Object.defineProperty(firstFrame.contentWindow, 'postMessage', { configurable: true, value: vi.fn() });
    sendMessage(firstFrame, DRAWIO_ORIGIN, { event: 'init' });
    expect(onImportConsumed).toHaveBeenCalledWith(9);
    first.unmount();

    const { frame, postMessage } = mountEditor({ importRequest: 0 });
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });

    expect(postMessage).toHaveBeenCalledWith(expect.stringContaining('"action":"load"'), DRAWIO_ORIGIN);
    expect(postMessage).not.toHaveBeenCalledWith(expect.stringContaining('"descriptor"'), DRAWIO_ORIGIN);
  });

  it('requests a trusted export and downloads only a matching data URI export event', () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { frame, postMessage } = mountEditor();
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });

    fireEvent.click(screen.getByRole('button', { name: '导出 PNG' }));
    expect(postMessage).toHaveBeenCalledWith(
      expect.stringContaining('"action":"export"'),
      DRAWIO_ORIGIN
    );

    sendMessage(frame, 'https://untrusted.example', { event: 'export', data: 'data:image/png;base64,aGVsbG8=' });
    expect(click).not.toHaveBeenCalled();

    sendMessage(frame, DRAWIO_ORIGIN, { event: 'export', data: 'data:image/png;base64,aGVsbG8=' });
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalledOnce();
  });

  it('accepts raw XML only as a validated Draw.io protocol exception and still validates XML data URIs', () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { frame } = mountEditor();
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });

    fireEvent.click(screen.getByRole('button', { name: '导出 Draw.io XML' }));
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'export', data: '<not-a-drawio-file />' });
    expect(click).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '导出 Draw.io XML' }));
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'export', data: '<mxfile />' });
    expect(click).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: '导出 Draw.io XML' }));
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'export', data: 'data:text/html;base64,PGgxPm5vcGU8L2gxPg==' });
    expect(click).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: '导出 Draw.io XML' }));
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'export', data: 'data:application/xml;base64,PG14ZmlsZSAvPg==' });
    expect(click).toHaveBeenCalledTimes(2);
  });

  it('prevents overlapping export requests until the trusted response is handled', () => {
    const { frame, postMessage } = mountEditor();
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'init' });

    fireEvent.click(screen.getByRole('button', { name: '导出 PNG' }));
    fireEvent.click(screen.getByRole('button', { name: '导出 SVG' }));

    expect(postMessage).toHaveBeenCalledTimes(2); // init load + one export; SVG remains disabled while PNG is pending.
    expect(screen.getByRole('button', { name: '导出 SVG' })).toBeDisabled();
  });

  it('removes the message listener and pending autosave on unmount', () => {
    const view = render(<DrawioEditor mermaidCode="flowchart TD\n A-->B" />);
    const frame = screen.getByTitle('Iris Draw.io 专业流程图') as HTMLIFrameElement;
    Object.defineProperty(frame.contentWindow, 'postMessage', { configurable: true, value: vi.fn() });
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'autosave', xml: '<mxfile />' });
    view.unmount();
    sendMessage(frame, DRAWIO_ORIGIN, { event: 'autosave', xml: '<mxfile id="ignored" />' });
    act(() => vi.runAllTimers());

    expect(JSON.parse(localStorage.getItem(DRAWIO_STORAGE_KEY) || '{}')).toMatchObject({ xml: '<mxfile />' });
  });
});
