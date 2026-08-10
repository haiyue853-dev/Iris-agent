import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import UmlFlowPage from './UmlFlowPage';

const savedDiagram = vi.fn(() => false);
const { renderMermaid } = vi.hoisted(() => ({ renderMermaid: vi.fn().mockResolvedValue({ svg: '<svg />' }) }));
const { onDrawioProps } = vi.hoisted(() => ({ onDrawioProps: vi.fn() }));

vi.mock('mermaid', () => ({
  default: { initialize: vi.fn(), render: renderMermaid },
}));

vi.mock('@xyflow/react', () => ({
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
  addEdge: vi.fn(),
}));

vi.mock('./DrawioEditor', () => ({
  default: (props: {
    mermaidCode: string;
    importRequest: number;
    onImportConsumed?: (request: number) => void;
    onDiagramPresenceChange?: (hasContent: boolean) => void;
  }) => {
    onDrawioProps(props);
    return <div data-testid="drawio-editor" data-mermaid={props.mermaidCode} data-import-request={props.importRequest} />;
  },
}));

vi.mock('./drawioStorage', () => ({ hasSavedDrawioDiagram: () => savedDiagram() }));

vi.mock('./FlowCanvas', () => ({ default: () => <div data-testid="classic-flow-canvas" />, makeEdge: vi.fn(), styleEdge: vi.fn() }));
vi.mock('./ShapePalette', () => ({ default: () => <div /> }));
vi.mock('./PropertiesPanel', () => ({ default: () => <div /> }));
vi.mock('./ContextMenu', () => ({ default: () => <div /> }));

describe('UmlFlowPage professional editor mode', () => {
  beforeEach(() => {
    localStorage.clear();
    savedDiagram.mockReturnValue(false);
    onDrawioProps.mockClear();
    renderMermaid.mockClear();
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('uses the professional canvas by default and keeps a classic canvas switch', () => {
    render(<UmlFlowPage />);

    expect(screen.getByTestId('drawio-editor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '经典画布' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '经典画布' }));
    expect(screen.queryByTestId('drawio-editor')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '专业画布' })).toBeInTheDocument();
  });

  it('shows an explicit Mermaid import action and confirms before replacing a saved Draw.io diagram', () => {
    savedDiagram.mockReturnValue(true);
    const confirm = vi.fn(() => false);
    vi.stubGlobal('confirm', confirm);
    render(<UmlFlowPage />);

    fireEvent.change(screen.getByLabelText('Mermaid 源码'), { target: { value: 'flowchart TD\n A-->B' } });
    fireEvent.click(screen.getByRole('button', { name: '导入到专业画布' }));

    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.getByTestId('drawio-editor')).toHaveAttribute('data-import-request', '0');

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '导入到专业画布' }));
    expect(Number(screen.getByTestId('drawio-editor').getAttribute('data-import-request'))).toBeGreaterThan(0);
    expect(screen.getByTestId('drawio-editor')).toHaveAttribute('data-mermaid', 'flowchart TD\n A-->B');
  });

  it('renders a non-flowchart Mermaid preview when switching from professional to classic mode', () => {
    render(<UmlFlowPage />);

    fireEvent.change(screen.getByLabelText('Mermaid 源码'), { target: { value: 'classDiagram\n  class User' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'classDiagram' } });
    fireEvent.click(screen.getByRole('button', { name: '经典画布' }));

    expect(renderMermaid).toHaveBeenCalledWith(expect.any(String), 'classDiagram\n  class User');
  });

  it('consumes an import command before switching away so remounting professional mode cannot replay Mermaid', () => {
    render(<UmlFlowPage />);

    fireEvent.change(screen.getByLabelText('Mermaid 源码'), { target: { value: 'flowchart TD\n A-->B' } });
    fireEvent.click(screen.getByRole('button', { name: '导入到专业画布' }));
    const importProps = onDrawioProps.mock.calls.at(-1)?.[0] as { importRequest: number; onImportConsumed?: (request: number) => void };
    expect(importProps.importRequest).toBeGreaterThan(0);
    expect(importProps.onImportConsumed).toBeTypeOf('function');

    importProps.onImportConsumed?.(importProps.importRequest);
    fireEvent.click(screen.getByRole('button', { name: '经典画布' }));
    fireEvent.click(screen.getByRole('button', { name: '专业画布' }));

    const remountedProps = onDrawioProps.mock.calls.at(-1)?.[0] as { importRequest: number };
    expect(remountedProps.importRequest).toBe(0);
  });

  it('requires confirmation when the professional canvas reports unsaved autosave content', () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal('confirm', confirm);
    render(<UmlFlowPage />);
    const drawioProps = onDrawioProps.mock.calls.at(-1)?.[0] as { onDiagramPresenceChange?: (hasContent: boolean) => void };

    act(() => drawioProps.onDiagramPresenceChange?.(true));
    fireEvent.change(screen.getByLabelText('Mermaid 源码'), { target: { value: 'flowchart TD\n A-->B' } });
    fireEvent.click(screen.getByRole('button', { name: '导入到专业画布' }));

    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.getByTestId('drawio-editor')).toHaveAttribute('data-import-request', '0');
  });
});
