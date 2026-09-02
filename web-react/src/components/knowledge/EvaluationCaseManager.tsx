import { useState } from 'react';

import type { KnowledgeEvaluationCase, KnowledgeEvaluationCaseValidation } from '../../api/knowledge';

type Props = {
  cases: KnowledgeEvaluationCase[];
  validation: KnowledgeEvaluationCaseValidation | null;
  onChange: (cases: KnowledgeEvaluationCase[]) => void;
  onLabel: (question: string) => void;
  onLabelMany: (questions: string[]) => void;
  onValidate: () => void;
  onRun: () => void;
  validating?: boolean;
  running?: boolean;
};

function isAnnotated(item: KnowledgeEvaluationCase): boolean {
  return Boolean(item.expected_title || item.expected_document_id || item.relevant_titles?.length || item.relevant_document_ids?.length || item.relevant_chunk_ids?.length);
}

export function EvaluationCaseManager({ cases, validation, onChange, onLabel, onLabelMany, onValidate, onRun, validating = false, running = false }: Props) {
  const [newQuestion, setNewQuestion] = useState('');
  const normalizedQuestions = cases.map((item) => item.question.trim().toLocaleLowerCase());
  const duplicateQuestions = new Set(normalizedQuestions.filter((question, index) => question && normalizedQuestions.indexOf(question) !== index));
  for (const question of normalizedQuestions) if (normalizedQuestions.filter((item) => item === question).length > 1) duplicateQuestions.add(question);
  const annotated = cases.filter(isAnnotated).length;
  const unannotatedQuestions = cases.filter((item) => !isAnnotated(item)).map((item) => item.question).filter(Boolean);
  const update = (index: number, patch: Partial<KnowledgeEvaluationCase>) => onChange(cases.map((item, rowIndex) => rowIndex === index ? { ...item, ...patch } : item));
  const add = () => {
    const question = newQuestion.trim();
    if (!question || cases.length >= 200) return;
    onChange([...cases, { question }]);
    setNewQuestion('');
  };

  return <section className="knowledge-evaluation-manager" aria-label="评测集管理">
    <header><div><strong>评测集管理</strong><span>已标注 {annotated}/50</span></div><small>当前知识库共 {cases.length} 题，最多支持 200 题。</small></header>
    <div className="knowledge-evaluation-manager-add"><input aria-label="新增评测问题" value={newQuestion} onChange={(event) => setNewQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') add(); }} placeholder="输入真实用户问题" /><button type="button" onClick={add} disabled={!newQuestion.trim() || cases.length >= 200}>添加问题</button></div>
    {cases.length ? <div className="knowledge-evaluation-table-wrap"><table><thead><tr><th>#</th><th>问题</th><th>预期标题</th><th>相关切片 ID</th><th>状态</th><th>操作</th></tr></thead><tbody>{cases.map((item, index) => {
      const serverRow = validation?.rows.find((row) => row.index === index);
      const duplicate = serverRow?.duplicate ?? duplicateQuestions.has(normalizedQuestions[index]);
      const empty = serverRow?.empty_annotation ?? !isAnnotated(item);
      const invalidIds = serverRow?.invalid_chunk_ids || [];
      return <tr key={`${index}-${item.question}`}><td>{index + 1}</td><td><input aria-label={`问题 ${index + 1}`} value={item.question} onChange={(event) => update(index, { question: event.target.value })} /></td><td><input aria-label={`预期标题 ${index + 1}`} value={item.expected_title || ''} onChange={(event) => update(index, { expected_title: event.target.value || undefined })} /></td><td><input aria-label={`相关切片 ${index + 1}`} value={(item.relevant_chunk_ids || []).join(',')} onChange={(event) => update(index, { relevant_chunk_ids: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) })} /></td><td><div className="knowledge-evaluation-case-status">{duplicate && <span>重复问题</span>}{empty && <span>空标注</span>}{invalidIds.length > 0 && <span>失效切片：{invalidIds.join(', ')}</span>}{!duplicate && !empty && !invalidIds.length && <span className="ready">已标注</span>}</div></td><td><div className="knowledge-evaluation-case-actions"><button type="button" aria-label={`标注问题 ${index + 1}`} onClick={() => onLabel(item.question)}>标注</button><button type="button" aria-label={`删除问题 ${index + 1}`} onClick={() => onChange(cases.filter((_, rowIndex) => rowIndex !== index))}>删除</button></div></td></tr>;
    })}</tbody></table></div> : <p className="knowledge-evaluation-manager-empty">还没有评测问题，可以手动添加或导入 JSON/CSV。</p>}
    <footer>{unannotatedQuestions.length > 0 && <button type="button" onClick={() => onLabelMany(unannotatedQuestions)}>批量标注 {unannotatedQuestions.length} 个未完成问题</button>}<button type="button" onClick={onValidate} disabled={!cases.length || validating}>{validating ? '检查中…' : '检查评测集'}</button><button type="button" onClick={onRun} disabled={!cases.length || running}>{running ? '评测中…' : '运行全部评测'}</button>{validation && <span>重复 {validation.summary.duplicates} · 空标注 {validation.summary.empty_annotations} · 失效切片 {validation.summary.invalid_chunks}</span>}</footer>
  </section>;
}
