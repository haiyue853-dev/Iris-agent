import { useState } from 'react';

import { debugKnowledgeSearch, recordKnowledgeBadCase, type RetrievalDebugTrace } from '../../api/knowledge';

const TOP_K = [1, 3, 5, 10];

export function RetrievalDebugger({ collectionId, onOpenSource }: { collectionId?: string; onOpenSource: (documentId: string, chunkId: string) => void }) {
  const [question, setQuestion] = useState('');
  const [trace, setTrace] = useState<RetrievalDebugTrace | null>(null);
  const [expectedChunkId, setExpectedChunkId] = useState('');
  const [reason, setReason] = useState('');
  const [running, setRunning] = useState(false);
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState('');

  const run = async () => {
    if (!question.trim()) return;
    setRunning(true); setMessage(''); setExpectedChunkId('');
    try { setTrace(await debugKnowledgeSearch(question.trim(), collectionId, 10)); }
    catch (error) { setMessage(error instanceof Error ? error.message : '检索调试失败'); }
    finally { setRunning(false); }
  };
  const finalCandidates = trace?.stages.find((stage) => stage.key === 'final')?.candidates || [];
  const allCandidates = trace?.stages.flatMap((stage) => stage.candidates) || [];
  const expectedRank = expectedChunkId ? finalCandidates.find((candidate) => candidate.chunk_id === expectedChunkId)?.rank : undefined;
  const saveBadCase = async () => {
    if (!trace) return;
    setRecording(true); setMessage('');
    const expected = allCandidates.find((candidate) => candidate.chunk_id === expectedChunkId);
    try {
      await recordKnowledgeBadCase({ question: trace.query, collection_id: collectionId || null,
        expected_title: expected?.title || null, relevant_chunk_ids: expectedChunkId ? [expectedChunkId] : [],
        relevant_document_ids: expected ? [expected.document_id] : [], expected_answer: '',
        actual_answer: finalCandidates[0]?.content || '', reason: reason.trim() || (expectedRank ? `正确切片位于第 ${expectedRank} 位` : '正确切片未进入最终 Top 10') });
      setMessage('已加入 Bad Case。');
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存 Bad Case 失败'); }
    finally { setRecording(false); }
  };

  return <details className="knowledge-retrieval-debugger">
    <summary>检索调试台</summary>
    <p>查看同一个问题在关键词、向量、融合、重排和最终筛选中的排名变化。</p>
    <div className="knowledge-debug-query"><input aria-label="调试问题" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="输入真实用户问题" onKeyDown={(event) => { if (event.key === 'Enter') void run(); }} /><button type="button" aria-label="运行检索调试" onClick={() => void run()} disabled={running || !question.trim()}>{running ? '运行中…' : '运行调试'}</button></div>
    {message && <p className="knowledge-debug-message" role="status">{message}</p>}
    {trace && <>
      <div className="knowledge-debug-summary"><span>候选上限 {trace.candidate_limit}</span><span>最终返回 {finalCandidates.length}</span><span>总耗时 {trace.elapsed_ms} ms</span>{expectedChunkId ? TOP_K.map((k) => <b key={k} className={expectedRank && expectedRank <= k ? 'hit' : 'miss'}>Top {k} {expectedRank && expectedRank <= k ? '命中' : '未命中'}</b>) : <small>请在任一阶段标记正确切片</small>}</div>
      <div className="knowledge-debug-stages">{trace.stages.map((stage) => <section key={stage.key} data-stage={stage.key}><header><strong>{stage.label}</strong><span>{stage.enabled ? `${stage.candidates.length} 条 · ${stage.elapsed_ms} ms` : '未启用'}</span></header>{stage.candidates.length ? <ol>{stage.candidates.map((candidate) => <li key={candidate.chunk_id}><span className="knowledge-debug-rank">#{candidate.rank}</span><div><b>{candidate.title}</b>{candidate.location && <small>{candidate.location}</small>}<p>{candidate.content}</p><small>{candidate.routes.join(' + ') || stage.label} · 分数 {candidate.score.toFixed(4)}</small><div><button type="button" aria-label={`标记 ${candidate.chunk_id} 为正确切片（${stage.label}）`} className={expectedChunkId === candidate.chunk_id ? 'active' : ''} onClick={() => setExpectedChunkId(candidate.chunk_id)}>标记正确</button><button type="button" aria-label={`打开切片 ${candidate.chunk_id}（${stage.label}）`} onClick={() => onOpenSource(candidate.document_id, candidate.chunk_id)}>打开原文</button></div></div></li>)}</ol> : <p className="knowledge-empty">{stage.enabled ? '此阶段没有召回结果' : '该检索能力未启用'}</p>}</section>)}</div>
      <div className="knowledge-debug-bad-case"><input aria-label="Bad Case 原因" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="失败原因（可选）" maxLength={1000} /><button type="button" onClick={() => void saveBadCase()} disabled={recording}>{recording ? '保存中…' : '加入 Bad Case'}</button></div>
    </>}
  </details>;
}
