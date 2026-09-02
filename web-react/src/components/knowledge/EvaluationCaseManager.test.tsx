import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EvaluationCaseManager } from './EvaluationCaseManager';

const cases = [
  { question: '什么时候发布？', expected_title: '发布计划', relevant_chunk_ids: ['chunk-1'] },
  { question: '什么时候发布？', expected_title: '发布计划' },
  { question: '负责人是谁？' },
];

describe('EvaluationCaseManager', () => {
  it('shows progress and validation problems for a knowledge evaluation suite', () => {
    render(<EvaluationCaseManager cases={cases} validation={{ summary: { total: 3, annotated: 2, duplicates: 2, empty_annotations: 1, invalid_chunks: 1 }, rows: [
      { index: 0, duplicate: true, empty_annotation: false, invalid_chunk_ids: ['chunk-1'] },
      { index: 1, duplicate: true, empty_annotation: false, invalid_chunk_ids: [] },
      { index: 2, duplicate: false, empty_annotation: true, invalid_chunk_ids: [] },
    ] }} onChange={vi.fn()} onLabel={vi.fn()} onLabelMany={vi.fn()} onValidate={vi.fn()} onRun={vi.fn()} />);

    expect(screen.getByText('已标注 2/50')).toBeInTheDocument();
    expect(screen.getAllByText('重复问题')).toHaveLength(2);
    expect(screen.getByText('空标注')).toBeInTheDocument();
    expect(screen.getByText(/失效切片：chunk-1/)).toBeInTheDocument();
  });

  it('adds, edits, deletes and sends a case to chunk labeling', async () => {
    const onChange = vi.fn();
    const onLabel = vi.fn();
    const user = userEvent.setup();
    render(<EvaluationCaseManager cases={[cases[0]]} validation={null} onChange={onChange} onLabel={onLabel} onLabelMany={vi.fn()} onValidate={vi.fn()} onRun={vi.fn()} />);

    await user.type(screen.getByLabelText('新增评测问题'), '缓存穿透怎么办？');
    await user.click(screen.getByRole('button', { name: '添加问题' }));
    expect(onChange).toHaveBeenLastCalledWith([...cases.slice(0, 1), { question: '缓存穿透怎么办？' }]);

    fireEvent.change(screen.getByLabelText('问题 1'), { target: { value: '发布日期是什么？' } });
    expect(onChange).toHaveBeenLastCalledWith([{ ...cases[0], question: '发布日期是什么？' }]);

    await user.click(screen.getByRole('button', { name: '标注问题 1' }));
    expect(onLabel).toHaveBeenCalledWith('什么时候发布？');
    await user.click(screen.getByRole('button', { name: '删除问题 1' }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('starts a labeling queue for every unannotated question', async () => {
    const onLabelMany = vi.fn();
    const user = userEvent.setup();
    render(<EvaluationCaseManager cases={[{ question: '问题一' }, { question: '问题二' }, cases[0]]} validation={null} onChange={vi.fn()} onLabel={vi.fn()} onLabelMany={onLabelMany} onValidate={vi.fn()} onRun={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: '批量标注 2 个未完成问题' }));

    expect(onLabelMany).toHaveBeenCalledWith(['问题一', '问题二']);
  });
});
