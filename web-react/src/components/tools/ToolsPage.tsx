import { useCallback, useEffect, useState } from 'react';

import { listAvailableTools, type AvailableTool } from '../../api/tools';

export default function ToolsPage() {
  const [tools, setTools] = useState<AvailableTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTools(await listAvailableTools());
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法加载可用工具');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="tools-page" aria-label="工具">
      <header className="tools-page-head">
        <span className="tools-eyebrow">RUNTIME CAPABILITIES</span>
        <h1>工具</h1>
        <p>当前 Agent 可以调用的工具会随运行配置自动更新。</p>
      </header>

      {error && (
        <div className="tools-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void load()}>重新加载</button>
        </div>
      )}

      {loading ? (
        <p className="tools-loading" role="status">正在加载工具…</p>
      ) : tools.length ? (
        <section className="tools-list" aria-label="可用工具列表">
          <div className="tools-list-head">
            <h2>当前可用</h2>
            <span>{tools.length} 个工具</span>
          </div>
          <div className="tools-grid">
            {tools.map((tool) => (
              <article className="tool-card" key={tool.name}>
                <div className="tool-card-head">
                  <code>{tool.name}</code>
                  <span className={tool.requires_approval ? 'tool-approval' : 'tool-direct'}>
                    {tool.requires_approval ? '需确认' : '直接可用'}
                  </span>
                </div>
                <p>{tool.description || '暂无说明'}</p>
              </article>
            ))}
          </div>
        </section>
      ) : (
        <p className="tools-empty">当前没有可用工具。</p>
      )}
    </section>
  );
}
