import { useEffect, useState } from 'react';

import { getKnowledgeChunkRevisions, restoreKnowledgeChunkRevision, updateKnowledgeChunk, type KnowledgeChunkRevision } from '../../api/knowledge';

type Chunk = { id: string; content: string; location?: string | null };

export function KnowledgeChunkEditor({ documentId, chunk, index, active, onUpdated, elementRef }: { documentId: string; chunk: Chunk; index: number; active: boolean; onUpdated: (chunk: Chunk) => void; elementRef?: (element: HTMLElement | null) => void }) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(chunk.content);
  const [location, setLocation] = useState(chunk.location || '');
  const [saving, setSaving] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [revisions, setRevisions] = useState<KnowledgeChunkRevision[]>([]);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { setContent(chunk.content); setLocation(chunk.location || ''); }, [chunk.content, chunk.location]);

  const save = async () => {
    if (!content.trim()) return;
    setSaving(true); setError('');
    try {
      const result = await updateKnowledgeChunk(documentId, chunk.id, content.trim(), location.trim() || null);
      onUpdated(result.chunk);
      setRevisions(result.revisions);
      setEditing(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存切片失败'); }
    finally { setSaving(false); }
  };
  const toggleHistory = async () => {
    const nextOpen = !historyOpen;
    setHistoryOpen(nextOpen);
    if (!nextOpen) return;
    setHistoryLoading(true); setError('');
    try { setRevisions(await getKnowledgeChunkRevisions(documentId, chunk.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '读取切片历史失败'); }
    finally { setHistoryLoading(false); }
  };
  const restore = async (revisionId: string) => {
    setRestoringId(revisionId); setError('');
    try {
      const result = await restoreKnowledgeChunkRevision(documentId, chunk.id, revisionId);
      onUpdated(result.chunk);
      setRevisions(result.revisions);
      setHistoryOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '恢复切片失败'); }
    finally { setRestoringId(null); }
  };

  return <article className="knowledge-source-chunk" data-citation-target={active} ref={elementRef}>
    {editing ? <div className="knowledge-chunk-edit"><label>位置<input aria-label={`切片位置 ${index + 1}`} value={location} onChange={(event) => setLocation(event.target.value)} maxLength={500} /></label><label>内容<textarea aria-label={`切片内容 ${index + 1}`} value={content} onChange={(event) => setContent(event.target.value)} rows={7} maxLength={50000} /></label><div><button type="button" aria-label={`保存切片 ${index + 1}`} onClick={() => void save()} disabled={saving || !content.trim()}>{saving ? '保存中…' : '保存'}</button><button type="button" onClick={() => { setEditing(false); setContent(chunk.content); setLocation(chunk.location || ''); }}>取消</button></div></div> : <>{chunk.location && <small>{chunk.location}</small>}<p>{chunk.content}</p>{!chunk.location && <small>切片 {index + 1}</small>}<div className="knowledge-chunk-actions"><button type="button" aria-label={`编辑切片 ${index + 1}`} onClick={() => setEditing(true)}>编辑</button><button type="button" aria-label={`查看切片 ${index + 1} 历史`} onClick={() => void toggleHistory()}>{historyOpen ? '收起历史' : '历史'}</button></div></>}
    {error && <p className="knowledge-chunk-error">{error}</p>}
    {historyOpen && <div className="knowledge-chunk-revisions">{historyLoading ? <small>正在读取历史…</small> : revisions.length ? revisions.map((revision) => <article key={revision.id}><small>{new Date(revision.created_at * 1000).toLocaleString()}{revision.location ? ` · ${revision.location}` : ''}</small><p>{revision.content}</p><button type="button" aria-label={`恢复切片 ${index + 1} 的此版本`} onClick={() => void restore(revision.id)} disabled={restoringId === revision.id}>{restoringId === revision.id ? '恢复中…' : '恢复此版本'}</button></article>) : <small>暂无历史版本</small>}</div>}
  </article>;
}
