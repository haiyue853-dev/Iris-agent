import { describe, expect, it } from 'vitest';

import { parseEvaluationDataset, serializeEvaluationDataset } from './evaluation-dataset';

const cases = [{
  question: '缓存穿透，怎么解决？',
  expected_title: 'Redis "实战"',
  relevant_document_ids: ['document-1'],
  relevant_chunk_ids: ['chunk-1', 'chunk-2'],
  expected_answer: '使用布隆过滤器，或缓存空值。\n还应限制恶意请求。',
}];

describe('evaluation dataset files', () => {
  it.each(['json', 'csv'] as const)('round-trips chunk ground truth through %s', (format) => {
    const exported = serializeEvaluationDataset(cases, format);

    expect(parseEvaluationDataset(exported, `evaluation.${format}`)).toEqual(cases);
  });

  it('rejects a dataset without valid questions', () => {
    expect(() => parseEvaluationDataset('{"cases":[{"question":""}]}', 'empty.json')).toThrow('评测集没有有效问题');
  });
});
