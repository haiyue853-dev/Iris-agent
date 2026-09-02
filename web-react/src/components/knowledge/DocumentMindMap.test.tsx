import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DocumentMindMap from './DocumentMindMap';

const nodes = [
  { id: 'root', parent_id: null, label: 'Iris 知识库设计', summary: '全文总结', kind: 'root' as const, ordinal: 0, evidence_chunk_ids: [] },
  { id: 'branch-1', parent_id: 'root', label: '知识组织', summary: '主题总结', kind: 'branch' as const, ordinal: 0, evidence_chunk_ids: ['chunk-1'] },
  { id: 'point-1-1', parent_id: 'branch-1', label: '文档思维导图', summary: '关键观点', kind: 'point' as const, ordinal: 0, evidence_chunk_ids: ['chunk-1'] },
];

describe('DocumentMindMap', () => {
  it('renders a hierarchical map and opens node evidence', () => {
    const onOpenEvidence = vi.fn();
    render(<DocumentMindMap nodes={nodes} onOpenEvidence={onOpenEvidence} />);

    expect(screen.getByRole('tree', { name: '文档思维导图' })).toBeInTheDocument();
    expect(screen.getByText('知识组织')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '文档思维导图' }));
    expect(screen.getByText('关键观点')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看“文档思维导图”的原文证据' }));
    expect(onOpenEvidence).toHaveBeenCalledWith(['chunk-1']);
  });
});
