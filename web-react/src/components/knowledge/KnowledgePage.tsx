import { useCallback, useEffect, useState } from 'react';
import { createKnowledge, deleteKnowledge, getKnowledge, listKnowledge, searchKnowledge, uploadKnowledge, getKnowledgeGraph, listKnowledgeTopics } from '../../api/knowledge';
import type { KnowledgeDetail, KnowledgeEntry, KnowledgeSearchHit } from '../../types';

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function KnowledgePage() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [selected, setSelected] = useState<KnowledgeDetail | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [question, setQuestion] = useState('');
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [topics, setTopics] = useState<string[]>([]);
  const [topic, setTopic] = useState('');
  const [graph, setGraph] = useState<{ nodes: { id: string; label: string; kind: string; document_count: number }[]; edges: { source: string; target: string; relation: string }[] }>({ nodes: [], edges: [] });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await listKnowledge());
      setError(false);
    } catch {
      setError(true);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void listKnowledgeTopics().then(setTopics).catch(() => setTopics([])); }, [entries.length]);
  useEffect(() => { void getKnowledgeGraph(topic || undefined).then(setGraph).catch(() => setGraph({ nodes: [], edges: [] })); }, [topic, entries.length]);

  const openDetail = async (id: string) => {
    try {
      setSelected(await getKnowledge(id));
      setError(false);
    } catch {
      setError(true);
    }
  };

  const add = async () => {
    const t = title.trim();
    const c = content.trim();
    if (!t || !c) return;
    try {
      const created = await createKnowledge({
        title: t,
        content: c,
        category: category.trim() || undefined,
        sourceUrl: sourceUrl.trim() || undefined,
      });
      setTitle('');
      setContent('');
      setSourceUrl('');
      setEntries((prev) => [created, ...prev]);
      setError(false);
    } catch {
      setError(true);
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteKnowledge(id);
      setEntries((prev) => prev.filter((entry) => entry.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch {
      setError(true);
    }
  };

  const ask = async () => {
    const q = question.trim();
    if (!q) return;
    setSearching(true);
    try {
      setHits(await searchKnowledge(q));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setSearching(false);
    }
  };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try { const document = await uploadKnowledge(file); setEntries((prev) => [document, ...prev]); setError(false); }
    catch { setError(true); } finally { setUploading(false); }
  };

  return (
    <section className="knowledge-page" aria-label="知识库">
      <header className="knowledge-header">
        <div><span>LOCAL KNOWLEDGE</span><h1>知识库</h1><p>归档、检索并连接你的本地资料。</p></div>
        <label className="knowledge-upload-button">{uploading ? '正在导入…' : '导入资料'}<input type="file" accept=".pdf,.docx,.xlsx,.xls,.md,.txt" onChange={(event) => void upload(event.target.files?.[0])} disabled={uploading} /></label>
      </header>

      {error && <div className="knowledge-error" role="alert">知识库服务暂不可用。</div>}
      <div className="knowledge-workspace">
      <aside className="knowledge-library"><div className="knowledge-library-title">主题 <span>{topics.length}</span></div><nav className="knowledge-topics" aria-label="知识主题"><button className={!topic ? 'active' : ''} onClick={() => setTopic('')}>全部资料</button>{topics.map((item) => <button key={item} className={topic === item ? 'active' : ''} onClick={() => setTopic(item)}>{item}</button>)}</nav></aside>
      <main className="knowledge-main">
      <div className="knowledge-ask">
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="搜索资料、主题或关系…" />
        <button onClick={() => void ask()} disabled={!question.trim() || searching}>{searching ? '检索中' : '检索'}</button>
      </div>
      <section className="knowledge-graph" aria-label="知识图谱"><div className="knowledge-graph-heading"><div><span>RELATION MAP</span><h2>{topic || '全部知识图谱'}</h2></div><small>{graph.nodes.length} 个节点 · {graph.edges.length} 条关系</small></div>{graph.nodes.length === 0 ? <p className="knowledge-empty">导入资料后自动生成图谱。</p> : <div className="knowledge-graph-nodes">{graph.nodes.map((node) => <span key={node.id} className={`knowledge-graph-node ${node.kind}`}>{node.label}<small>{node.document_count}</small></span>)}</div>}</section>

      <details className="knowledge-add"><summary>手动添加资料</summary><div className="knowledge-add-form">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题" maxLength={200} />
        <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="主题（可选）" maxLength={50} />
        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="来源链接（可选）" maxLength={2000} />
        <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="正文内容" rows={5} />
        <button onClick={() => void add()} disabled={!title.trim() || !content.trim()}>保存资料</button>
      </div></details>

      {hits !== null && (
        <div className="knowledge-hits">
          <h2>检索结果</h2>
          {hits.length === 0 ? (
            <p className="knowledge-empty">没有找到相关内容</p>
          ) : (
            <ul className="knowledge-hit-list">
              {hits.map((hit) => (
                <li key={(hit as KnowledgeSearchHit & { chunk_id?: string }).chunk_id || hit.entry_id} className="knowledge-hit-item">
                  <div className="knowledge-hit-title">{hit.title}</div>
                  <p className="knowledge-hit-content">{hit.content}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {loading ? (
        <p className="knowledge-empty">正在加载知识库…</p>
      ) : entries.length === 0 ? (
        <p className="knowledge-empty">知识库还是空的，抓取面经后保存，或手动添加。</p>
      ) : (
        <ul className="knowledge-list">
          {entries.map((entry) => (
            <li key={entry.id} className="knowledge-item">
              <button className="knowledge-item-main" onClick={() => void openDetail(entry.id)}>
                <span className="knowledge-item-title">{entry.title}</span>
                <span className="knowledge-item-meta">{entry.category || '文档'} · {entry.source_type === 'upload' ? '本地文件' : entry.source_type === 'scrape' ? '抓取' : '手动'}</span>
              </button>
              <span className="knowledge-item-time">{formatTime(entry.updated_at)}</span>
              <button className="knowledge-delete" onClick={() => void remove(entry.id)}>删除</button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="knowledge-detail">
          <div className="knowledge-detail-header">
            <h2>{selected.title}</h2>
            <button onClick={() => setSelected(null)}>关闭</button>
          </div>
          {selected.source_url && (
            <a href={selected.source_url} target="_blank" rel="noreferrer">查看原文</a>
          )}
          <pre className="knowledge-detail-content">{selected.content || (selected as KnowledgeDetail & { chunks?: { content: string }[] }).chunks?.map((item) => item.content).join('\n\n')}</pre>
        </div>
      )}
      </main></div>
    </section>
  );
}
