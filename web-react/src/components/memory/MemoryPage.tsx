import { useCallback, useEffect, useState } from 'react';
import { createMemory, deleteMemory, listMemories } from '../../api/memory';
import type { MemoryCategory, MemoryEntry } from '../../types';

const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  preference: '偏好',
  fact: '事实',
  project: '项目',
  other: '其他',
};

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [content, setContent] = useState('');
  const [category, setCategory] = useState<MemoryCategory>('fact');
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await listMemories());
      setError(false);
    } catch {
      setError(true);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const add = async () => {
    const text = content.trim();
    if (!text) return;
    try {
      const created = await createMemory(text, category);
      setContent('');
      setEntries((prev) => [created, ...prev]);
      setError(false);
    } catch {
      setError(true);
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteMemory(id);
      setEntries((prev) => prev.filter((entry) => entry.id !== id));
    } catch {
      setError(true);
    }
  };

  return (
    <section className="memory-page" aria-label="记忆">
      <header className="memory-header">
        <span>MEMORY</span>
        <h1>记忆</h1>
        <p>管理 Iris 跨会话记住的长期信息。</p>
      </header>
      {error && <div className="memory-error" role="alert">记忆服务暂不可用。</div>}
      <div className="memory-form">
        <input
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder="输入要记住的内容"
          maxLength={500}
        />
        <select value={category} onChange={(event) => setCategory(event.target.value as MemoryCategory)}>
          {(Object.keys(CATEGORY_LABELS) as MemoryCategory[]).map((item) => (
            <option key={item} value={item}>{CATEGORY_LABELS[item]}</option>
          ))}
        </select>
        <button onClick={() => void add()} disabled={!content.trim()}>添加记忆</button>
      </div>
      {loading ? (
        <p className="memory-empty">正在加载记忆…</p>
      ) : entries.length === 0 ? (
        <p className="memory-empty">还没有任何记忆</p>
      ) : (
        <ul className="memory-list">
          {entries.map((entry) => (
            <li key={entry.id} className="memory-item">
              <span className={`memory-category memory-category-${entry.category}`}>{CATEGORY_LABELS[entry.category]}</span>
              <span className="memory-content">{entry.content}</span>
              <button className="memory-delete" onClick={() => void remove(entry.id)}>删除</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
