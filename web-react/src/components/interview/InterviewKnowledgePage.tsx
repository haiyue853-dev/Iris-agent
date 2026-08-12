import { useEffect, useMemo, useState } from 'react';
import { listInterviewKnowledge } from '../../api/interviewKnowledge';
import type { InterviewKnowledgeItem } from '../../types';

export default function InterviewKnowledgePage() {
  const [items, setItems] = useState<InterviewKnowledgeItem[]>([]);
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [error, setError] = useState('');
  const load = async () => { try { setError(''); setItems(await listInterviewKnowledge()); } catch (cause) { setError(cause instanceof Error ? cause.message : '加载失败'); } };
  useEffect(() => { void load(); }, []);
  const topics = useMemo(() => [...new Set(items.map((item) => item.topic))], [items]);
  const visible = items.filter((item) => (!topic || item.topic === topic) && (!query || `${item.question} ${item.answer}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  return <section className="interview-knowledge-page"><header><div><p className="report-eyebrow">INTERVIEW REVIEW</p><h1>面试复习</h1><p>已保存 {items.length} 条问答；新资料可在聊天中让 Iris 收集。</p></div><button onClick={() => void load()}>刷新</button></header><div className="knowledge-filters"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索题目或答案" /><select value={topic} onChange={(event) => setTopic(event.target.value)}><option value="">全部主题</option>{topics.map((name) => <option key={name}>{name}</option>)}</select></div>{error ? <p className="knowledge-state">{error}</p> : <div className="knowledge-card-list">{visible.map((item, index) => <article className="knowledge-card" key={`${item.question}-${index}`}><small>{item.topic}</small><h2>{item.question}</h2><p>{item.answer}</p><a href={item.source_url} target="_blank" rel="noreferrer">查看来源</a></article>)}</div>}</section>;
}
