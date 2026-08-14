import { useEffect, useMemo, useState } from 'react';
import {
  getPracticeQuestion, listInterviewKnowledge, previewInterviewCollection,
  reviewInterviewQuestion, saveInterviewCollection,
} from '../../api/interviewKnowledge';
import type { InterviewCollectionPreview, InterviewKnowledgeItem, InterviewReviewState } from '../../types';

const itemKey = (item: { question: string; source_url: string }) => `${item.question}\n${item.source_url}`;

export default function InterviewKnowledgePage() {
  const [items, setItems] = useState<InterviewKnowledgeItem[]>([]);
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [collectionTopic, setCollectionTopic] = useState('');
  const [preview, setPreview] = useState<InterviewCollectionPreview | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [collecting, setCollecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [practicing, setPracticing] = useState(false);
  const [practiceItem, setPracticeItem] = useState<InterviewKnowledgeItem | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);

  const load = async () => {
    try { setError(''); setItems(await listInterviewKnowledge()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '加载失败'); }
  };
  useEffect(() => { void load(); }, []);

  const topics = useMemo(() => [...new Set(items.map((item) => item.topic))], [items]);
  const visible = items.filter((item) => (!topic || item.topic === topic)
    && (!query || `${item.question} ${item.answer}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())));

  const collect = async () => {
    if (!collectionTopic.trim()) return;
    try {
      setCollecting(true); setError(''); setNotice('');
      const value = await previewInterviewCollection(collectionTopic.trim());
      setPreview(value); setSelected(new Set(value.items.map(itemKey)));
    } catch (cause) { setError(cause instanceof Error ? cause.message : '采集失败'); }
    finally { setCollecting(false); }
  };

  const confirmSave = async () => {
    if (!preview) return;
    const chosen = preview.items.filter((item) => selected.has(itemKey(item)));
    if (!chosen.length) return;
    try {
      setSaving(true); setError('');
      const result = await saveInterviewCollection(preview.topic, chosen);
      setNotice(`已保存 ${result.added} 道题，知识库共 ${result.total} 道题。`);
      setPreview(null); setSelected(new Set()); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败'); }
    finally { setSaving(false); }
  };

  const toggleItem = (key: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const loadPractice = async () => {
    try { setError(''); setShowAnswer(false); setPracticeItem(await getPracticeQuestion(topic || undefined)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '加载复习题失败'); }
  };
  const startPractice = async () => { setPracticing(true); await loadPractice(); };
  const markPractice = async (reviewState: InterviewReviewState) => {
    if (!practiceItem) return;
    try { setError(''); await reviewInterviewQuestion(practiceItem.id, reviewState); await load(); await loadPractice(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '保存复习状态失败'); }
  };

  return (
    <section className="interview-knowledge-page">
      <header>
        <div><p className="report-eyebrow">INTERVIEW REVIEW</p><h1>面试知识库</h1><p>采集真实来源中的问题和答案，确认后保存用于复习。</p></div>
        <div className="knowledge-header-actions"><button onClick={() => void startPractice()}>开始复习</button><button onClick={() => void load()}>刷新</button></div>
      </header>

      <section className="collection-panel">
        <div className="collection-form">
          <input aria-label="采集主题" value={collectionTopic} onChange={(event) => setCollectionTopic(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void collect(); }} placeholder="输入岗位或技术栈，例如 AI Agent 开发" />
          <button disabled={collecting || !collectionTopic.trim()} onClick={() => void collect()}>{collecting ? '采集中...' : '采集预览'}</button>
        </div>
        {preview ? (
          <div className="collection-preview">
            <div className="collection-summary">
              <div><strong>{preview.topic}</strong><span>{preview.summary.sources} 个来源 · {preview.summary.found} 道新题 · {preview.summary.duplicates} 道重复</span></div>
              <div className="collection-actions">
                <button onClick={() => { setPreview(null); setSelected(new Set()); }}>取消</button>
                <button disabled={saving || selected.size === 0} onClick={() => void confirmSave()}>{saving ? '保存中...' : `确认保存 ${selected.size} 道`}</button>
              </div>
            </div>
            <div className="collection-source-list">
              {preview.sources.map((source) => <span className={source.status} key={source.url}>{source.title || source.url} · {source.status === 'ok' ? `${source.count} 道` : '失败'}</span>)}
            </div>
            <div className="collection-item-list">
              {preview.items.map((item) => {
                const key = itemKey(item);
                return <label className="collection-item" key={key}><input type="checkbox" checked={selected.has(key)} onChange={() => toggleItem(key)} /><span><strong>{item.question}</strong><small>{item.answer}</small></span></label>;
              })}
              {!preview.items.length ? <p className="knowledge-state">未提取到完整问答，请尝试更具体的主题。</p> : null}
            </div>
          </div>
        ) : null}
      </section>

      {notice ? <p className="knowledge-notice">{notice}</p> : null}
      {error ? <p className="knowledge-state">{error}</p> : null}
      <div className="knowledge-filters">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索题目或答案" />
        <select value={topic} onChange={(event) => { setTopic(event.target.value); setPracticeItem(null); }}><option value="">全部主题</option>{topics.map((name) => <option key={name}>{name}</option>)}</select>
      </div>

      {practicing ? (
        <section className="practice-card">
          <div className="practice-heading"><small>{practiceItem?.topic || topic || '全部主题'}</small><button className="practice-close" onClick={() => setPracticing(false)}>退出复习</button></div>
          {practiceItem ? <><p className="practice-label">先在心里回答，再查看参考答案</p><h2>{practiceItem.question}</h2>{showAnswer ? <div className="practice-answer"><strong>参考答案</strong><p>{practiceItem.answer}</p></div> : <button className="practice-reveal" onClick={() => setShowAnswer(true)}>查看答案</button>}{showAnswer ? <div className="practice-actions"><button onClick={() => void markPractice('known')}>会了</button><button onClick={() => void markPractice('learning')}>不会</button><button onClick={() => void markPractice('review')}>待复习</button></div> : null}</> : <p className="knowledge-state">当前主题没有到期的复习题。</p>}
        </section>
      ) : (
        <div className="knowledge-card-list">{visible.map((item) => <article className="knowledge-card" key={item.id}><small>{item.topic}</small><h2>{item.question}</h2><p>{item.answer}</p><a href={item.source_url} target="_blank" rel="noreferrer">查看来源</a></article>)}</div>
      )}
    </section>
  );
}
