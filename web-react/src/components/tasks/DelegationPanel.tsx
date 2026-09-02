import { useCallback, useEffect, useState } from 'react';

import { cancelDelegation, getDelegation, listDelegations } from '../../api/delegations';
import type { DelegationDetail, DelegationSummary } from '../../types';

const ACTIVE_STATUSES = new Set(['queued', 'running']);

function delegationTime(value: number) {
  const date = new Date(value * 1000);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString();
}

export default function DelegationPanel() {
  const [items, setItems] = useState<DelegationSummary[]>([]);
  const [detail, setDetail] = useState<DelegationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await listDelegations());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!detail || !ACTIVE_STATUSES.has(detail.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getDelegation(detail.id);
        setDetail(next);
        setItems((current) => current.map((item) => item.id === next.id ? next : item));
      } catch { /* Keep the last readable state during transient failures. */ }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [detail?.id, detail?.status]);

  const select = async (id: string) => {
    try {
      setDetail(await getDelegation(id));
      setError(false);
    } catch {
      setError(true);
    }
  };

  const cancel = async () => {
    if (!detail) return;
    setCancelling(true);
    try {
      const cancelled = await cancelDelegation(detail.id);
      setDetail(cancelled);
      setItems((current) => current.map((item) => item.id === cancelled.id ? cancelled : item));
    } catch {
      setError(true);
    } finally {
      setCancelling(false);
    }
  };

  if (loading) return <p className="task-center-loading">正在加载后台委派…</p>;
  if (error && !items.length) return <div className="task-center-error" role="alert">无法加载后台委派。<button onClick={() => void load()}>重试</button></div>;

  return <div className="task-center-layout">
    <section className="task-list" aria-label="后台委派列表">
      {items.length ? items.map((item) => <button key={item.id} className={`task-list-item ${detail?.id === item.id ? 'active' : ''}`} onClick={() => void select(item.id)}>
        <div><strong>{item.goal}</strong><span className={`task-status status-${item.status}`}>{item.status}</span></div>
        <small>{item.parent_task_id ? `父任务 ${item.parent_task_id} · ` : ''}{delegationTime(item.updated_at)}</small>
      </button>) : <p className="task-center-empty">暂无后台委派。</p>}
    </section>
    <section className="task-detail" aria-label="后台委派详情">
      {detail ? <><header><div><span>后台委派</span><h2>{detail.goal}</h2></div><span className={`task-status status-${detail.status}`}>{detail.status}</span></header>
        {detail.parent_task_id && <p>父任务 {detail.parent_task_id}</p>}
        {ACTIVE_STATUSES.has(detail.status) && <button className="task-cancel-btn" disabled={cancelling} onClick={() => void cancel()}>{cancelling ? '取消中…' : '取消委派'}</button>}
        {detail.result && <pre className="delegation-result">{detail.result}</pre>}
        {detail.error && detail.status !== 'cancelled' && <p className="task-center-error">{detail.error}</p>}
      </> : <p className="task-center-empty">选择一项后台委派查看结果。</p>}
    </section>
  </div>;
}
