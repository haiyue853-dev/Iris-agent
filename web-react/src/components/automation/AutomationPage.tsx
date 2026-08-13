import { useEffect, useMemo, useState } from 'react';
import {
  createAutomationTask, createRadarSubscription, deleteAutomationTask, deleteNotification, deleteRadarSubscription,
  listAutomationTasks, listNotifications, listRadarItems, listRadarSubscriptions, listTaskExecutions,
  markNotificationRead, runAutomationTask, setAutomationTaskEnabled,
  type AutomationExecution, type AutomationTask, type Notification, type RadarItem, type RadarSubscription,
} from '../../api/automation';

const defaultSchedule = '0 9 * * *';

export default function AutomationPage() {
  const [tasks, setTasks] = useState<AutomationTask[]>([]);
  const [subscriptions, setSubscriptions] = useState<RadarSubscription[]>([]);
  const [items, setItems] = useState<RadarItem[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [executions, setExecutions] = useState<Record<string, AutomationExecution[]>>({});
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [taskName, setTaskName] = useState('热点雷达扫描');
  const [schedule, setSchedule] = useState(defaultSchedule);
  const [keyword, setKeyword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [taskResult, subscriptionResult, itemResult, notificationResult] = await Promise.all([
        listAutomationTasks(), listRadarSubscriptions(), listRadarItems(), listNotifications(),
      ]);
      const histories = await Promise.all(taskResult.tasks.map(async (task) => [task.id, (await listTaskExecutions(task.id)).executions] as const));
      setTasks(taskResult.tasks); setSubscriptions(subscriptionResult.subscriptions); setItems(itemResult.items);
      setNotifications(notificationResult.notifications); setExecutions(Object.fromEntries(histories)); setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '无法加载自动化任务'); }
  };

  useEffect(() => { void load(); }, []);
  const unread = notifications.filter((item) => !item.read);
  const stats = useMemo(() => ({ enabled: tasks.filter((task) => task.enabled).length, completed: Object.values(executions).flat().filter((item) => item.status === 'succeeded').length, items: items.length }), [tasks, executions, items]);
  const itemById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const perform = async (action: () => Promise<unknown>, fallback: string) => { setBusy(true); try { await action(); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : fallback); } finally { setBusy(false); } };
  const addSubscription = () => keyword.trim() && void perform(async () => { await createRadarSubscription(keyword.trim()); setKeyword(''); }, '订阅保存失败');
  const addTask = () => void perform(() => createAutomationTask(taskName, schedule), '任务创建失败');
  const removeSubscription = (item: RadarSubscription) => window.confirm(`删除关键词订阅“${item.keyword}”？`) && void perform(() => deleteRadarSubscription(item.id), '订阅删除失败');
  const removeTask = (task: AutomationTask) => window.confirm(`删除例行任务“${task.name}”？`) && void perform(() => deleteAutomationTask(task.id), '任务删除失败');

  return <section className="automation-page" aria-label="自动化任务中心">
    <header className="automation-hero"><div><span className="automation-eyebrow">AGENT ROUTINES</span><h1>自动化任务</h1><p>把关注的热点变成可控、可追溯的 Agent 例行任务。</p></div><button className="automation-primary" onClick={() => document.getElementById('automation-create')?.scrollIntoView({ behavior: 'smooth' })}>新建扫描任务</button></header>
    {error && <div className="automation-error" role="alert">{error}</div>}
    {unread.length > 0 && <section className="automation-notifications" aria-label="站内通知"><div className="automation-panel-head"><div><span>NEW SIGNALS</span><h2>{unread.length} 条未读通知</h2></div><small>扫描发现新增热点时生成</small></div><div className="automation-notice-list">{unread.map((notice) => <article key={notice.id} className="automation-notice"><div><strong>{notice.title}</strong><p>{notice.summary}</p><div className="automation-notice-links">{notice.item_ids.map((id) => { const item = itemById.get(id); return item ? <a key={id} href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : null; })}</div></div><div className="automation-notice-actions"><button className="automation-secondary" disabled={busy} onClick={() => void perform(() => markNotificationRead(notice.id), '通知更新失败')}>标为已读</button><button className="automation-danger" disabled={busy} onClick={() => void perform(() => deleteNotification(notice.id), '通知删除失败')}>删除</button></div></article>)}</div></section>}
    <div className="automation-metrics"><Metric label="运行中的例行任务" value={stats.enabled} detail={`共 ${tasks.length} 个已配置`} /><Metric label="已完成执行" value={stats.completed} detail="保留每次扫描的结果" /><Metric label="雷达热点" value={stats.items} detail="命中订阅关键词的最新条目" /></div>
    <div className="automation-grid"><section className="automation-panel"><div className="automation-panel-head"><div><span>RADAR INPUT</span><h2>热点订阅</h2></div><small>订阅后由扫描任务统一处理</small></div><div className="automation-inline-form"><input aria-label="热点关键词" value={keyword} onChange={(event) => setKeyword(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && addSubscription()} placeholder="例如：MCP、AI Agent"/><button className="automation-secondary" disabled={busy} onClick={addSubscription}>添加</button></div><div className="automation-tags">{subscriptions.length ? subscriptions.map((item) => <span key={item.id}>{item.keyword}<button aria-label={`删除订阅 ${item.keyword}`} disabled={busy} onClick={() => removeSubscription(item)}>×</button></span>) : <p>还没有订阅关键词。</p>}</div></section><section id="automation-create" className="automation-panel"><div className="automation-panel-head"><div><span>NEW ROUTINE</span><h2>创建例行扫描</h2></div><small>使用五段 cron，例如 <code>0 9 * * *</code></small></div><div className="automation-create-form"><input aria-label="任务名称" value={taskName} onChange={(event) => setTaskName(event.target.value)} /><input aria-label="执行计划" value={schedule} onChange={(event) => setSchedule(event.target.value)} /><button className="automation-primary" disabled={busy} onClick={addTask}>保存任务</button></div></section></div>
    <section className="automation-panel automation-routines"><div className="automation-panel-head"><div><span>EXECUTION LEDGER</span><h2>例行任务</h2></div><small>服务启动后会自动按计划检查</small></div>{tasks.length ? <div className="automation-task-list">{tasks.map((task) => { const history = executions[task.id] || []; const latest = history[0]; const expanded = expandedTaskId === task.id; return <article key={task.id} className="automation-task"><div className="automation-task-content"><div className="automation-task-title"><strong>{task.name}</strong><span className={task.enabled ? 'is-active' : ''}>{task.enabled ? '已启用' : '已暂停'}</span></div><code>{task.schedule}</code><p>{latest ? `${latest.status === 'succeeded' ? '最近执行完成' : '最近执行：' + latest.status} · ${latest.summary || '暂无摘要'}` : '尚未执行'}</p>{expanded && <div className="automation-execution-list">{history.slice(0, 3).map((execution) => <div key={execution.id} className="automation-execution"><span className={`automation-status is-${execution.status}`}>{execution.status}</span><span>{execution.trigger}</span><span>{execution.new_count} 条新增</span>{execution.failed_sources.length > 0 && <span>失败来源：{execution.failed_sources.join('、')}</span>}<p>{execution.summary}</p></div>)}</div>}</div><div className="automation-task-actions"><button className="automation-secondary" onClick={() => setExpandedTaskId(expanded ? null : task.id)}>{expanded ? '收起详情' : '执行详情'}</button><button className="automation-secondary" disabled={busy} onClick={() => void perform(() => setAutomationTaskEnabled(task.id, !task.enabled), '任务更新失败')}>{task.enabled ? '暂停' : '启用'}</button><button className="automation-primary" disabled={busy} onClick={() => void perform(() => runAutomationTask(task.id), '执行失败')}>立即运行</button><button className="automation-danger" disabled={busy} onClick={() => removeTask(task)}>删除</button></div></article>; })}</div> : <div className="automation-empty"><strong>还没有例行任务</strong><p>先添加热点关键词，再创建一个按计划扫描的任务。</p></div>}</section>
    <section className="automation-panel automation-radar-results"><div className="automation-panel-head"><div><span>LATEST SIGNALS</span><h2>最新热点</h2></div><small>按订阅关键词过滤</small></div>{items.length ? <div className="automation-item-list">{items.slice(0, 6).map((item) => <a key={item.id} className="automation-item" href={item.url} target="_blank" rel="noreferrer"><span>{item.keyword}</span><div><strong>{item.title}</strong><p>{item.summary || item.source}</p></div><small>{item.source}</small></a>)}</div> : <div className="automation-empty"><strong>暂无热点命中</strong><p>添加关键词并运行一次扫描后，结果会显示在这里。</p></div>}</section>
  </section>;
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) { return <article className="automation-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
