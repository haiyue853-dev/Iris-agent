import { useCallback, useEffect, useRef, useState } from 'react';
import { getTask, listTasks } from '../../api/tasks';
import type { AgentTask, TaskDetail } from '../../types';

interface TaskCenterPageProps { selectedTaskId?: string | null; }

function taskTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export default function TaskCenterPage({ selectedTaskId }: TaskCenterPageProps) {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(selectedTaskId || null);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [listError, setListError] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequestId = useRef(0);
  const loadDetail = useCallback(async (taskId: string) => {
    const requestId = ++detailRequestId.current;
    setDetailLoading(true); setDetailError(false); setDetail(null);
    try {
      const loaded = await getTask(taskId);
      if (requestId === detailRequestId.current) setDetail(loaded);
    } catch {
      if (requestId === detailRequestId.current) setDetailError(true);
    } finally {
      if (requestId === detailRequestId.current) setDetailLoading(false);
    }
  }, []);
  const load = useCallback(async () => {
    setListLoading(true);
    try {
      const summaries = await listTasks(); setTasks(summaries);
      const taskId = selectedTaskId || summaries[0]?.id;
      setSelectedId(taskId || null);
      if (taskId) await loadDetail(taskId); else setDetail(null);
      setListError(false);
    } catch { setListError(true); setTasks([]); setDetail(null); } finally { setListLoading(false); }
  }, [loadDetail, selectedTaskId]);
  useEffect(() => { void load(); }, [load]);
  const select = (id: string) => { setSelectedId(id); void loadDetail(id); };
  return <section className="task-center-page" aria-label="任务中心">
    <header className="task-center-header"><span>AGENT TASKS</span><h1>任务中心</h1><p>查看聊天 Agent 的安全执行时间线。</p></header>
    {listError && <div className="task-center-error" role="alert">无法加载任务中心。<button onClick={() => void load()}>重试</button></div>}
    {!listError && listLoading && <p className="task-center-loading">正在加载任务…</p>}
    {!listError && !listLoading && <div className="task-center-layout"><section className="task-list" aria-label="任务列表">
      {tasks.length ? tasks.map((task) => <button key={task.id} className={`task-list-item ${selectedId === task.id ? 'active' : ''}`} onClick={() => select(task.id)}><div><strong>{task.request_summary}</strong><span className={`task-status status-${task.status}`}>{task.status}</span></div><small>会话 {task.session_id} · {taskTime(task.updated_at)}</small></button>) : <p className="task-center-empty">暂无可查看的任务。</p>}
    </section><section className="task-detail" aria-label="任务时间线">
      {detailLoading ? <p className="task-center-loading">正在加载详情…</p> : detailError ? <div className="task-center-error" role="alert">无法加载任务详情。<button onClick={() => selectedId && void loadDetail(selectedId)}>重试详情</button></div> : detail ? <><header><div><span>任务状态</span><h2>{detail.request_summary}</h2></div><span className={`task-status status-${detail.status}`}>{detail.status}</span></header><ol className="task-timeline">{detail.events.map((event) => <li key={event.id}><time>{taskTime(event.created_at)}</time><div><strong>{event.label}</strong>{event.tool_name && <span>{event.tool_name}</span>}{typeof event.duration_ms === 'number' && <small>{event.duration_ms} ms</small>}</div></li>)}</ol></> : <p className="task-center-empty">选择一项任务查看时间线。</p>}
    </section></div>}
  </section>;
}
