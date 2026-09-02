import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UmlFlowPage from './UmlFlowPage';

const { analyzeUml } = vi.hoisted(() => ({ analyzeUml: vi.fn() }));
const { onDrawioProps } = vi.hoisted(() => ({ onDrawioProps: vi.fn() }));

vi.mock('../../api/uml', () => ({ analyzeUml }));
vi.mock('./DrawioEditor', () => ({
  default: (props: { mermaidCode: string; importRequest: number }) => {
    onDrawioProps(props);
    return <div data-testid="drawio-editor" data-mermaid={props.mermaidCode} data-import-request={props.importRequest} />;
  },
}));
vi.mock('./drawioStorage', () => ({ hasSavedDrawioDiagram: () => false }));

describe('UmlFlowPage Draw.io workspace', () => {
  beforeEach(() => {
    onDrawioProps.mockClear();
    analyzeUml.mockReset();
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('shows only the Draw.io professional canvas', () => {
    render(<UmlFlowPage />);

    expect(document.querySelector('.uml-page')).toHaveClass('uml-page');
    expect(screen.getByTestId('drawio-editor')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '经典画布' })).not.toBeInTheDocument();
  });

  it('imports generated Mermaid into Draw.io automatically', async () => {
    analyzeUml.mockResolvedValue({ mermaid: 'flowchart TD\n A-->B' });
    render(<UmlFlowPage />);

    fireEvent.change(screen.getByPlaceholderText(/用户登录流程/), { target: { value: '登录流程' } });
    fireEvent.click(screen.getByRole('button', { name: '生成流程图' }));

    await waitFor(() => {
      expect(Number(screen.getByTestId('drawio-editor').getAttribute('data-import-request'))).toBeGreaterThan(0);
    });
    expect(screen.getByTestId('drawio-editor')).toHaveAttribute('data-mermaid', 'flowchart TD\n A-->B');
  });

  it('reimports edited Mermaid into Draw.io on demand', async () => {
    render(<UmlFlowPage />);

    fireEvent.change(screen.getByLabelText('Mermaid 源码'), { target: { value: 'flowchart TD\n A-->B' } });
    fireEvent.click(screen.getByRole('button', { name: '重新导入到专业画布' }));

    await waitFor(() => {
      expect(Number(screen.getByTestId('drawio-editor').getAttribute('data-import-request'))).toBeGreaterThan(0);
    });
    expect(screen.getByTestId('drawio-editor')).toHaveAttribute('data-mermaid', 'flowchart TD\n A-->B');
  });
});
