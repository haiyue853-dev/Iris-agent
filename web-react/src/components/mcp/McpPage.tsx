import { useEffect, useMemo, useState } from 'react';

import {
  createMcpServer,
  deleteMcpServer,
  discoverMcpTools,
  listMcpEvents,
  listMcpServers,
  setMcpAllowedTools,
  setMcpEnabled,
  setMcpEnvironment,
  setMcpHeaders,
  setMcpTimeout,
  type McpEvent,
  type McpServer,
  type McpTool,
} from '../../api/mcp';

export default function McpPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('Browser MCP');
  const [command, setCommand] = useState('node');
  const [args, setArgs] = useState('D:/agent/browser-mcp/browser-mcp-server-v2.js');
  const [transport, setTransport] = useState<'stdio' | 'http'>('stdio');
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [tools, setTools] = useState<Record<string, McpTool[]>>({});
  const [selectedTools, setSelectedTools] = useState<Record<string, string[]>>({});
  const [events, setEvents] = useState<Record<string, McpEvent[]>>({});

  const load = async () => {
    try {
      const loaded = (await listMcpServers()).servers;
      setServers(loaded);
      setTools(Object.fromEntries(loaded.filter((server) => (server.discovered_tools || []).length > 0).map((server) => [server.id, server.discovered_tools || []])));
      setSelectedTools(Object.fromEntries(loaded.map((server) => [server.id, server.allowed_tools])));
      const entries = await Promise.all(loaded.map(async (server) => [server.id, (await listMcpEvents(server.id)).events] as const));
      setEvents(Object.fromEntries(entries));
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法加载 MCP 配置');
    }
  };

  useEffect(() => { void load(); }, []);

  const summary = useMemo(() => {
    const configuredTools = Object.values(selectedTools).flat().length;
    const automaticTools = Object.values(tools).flat().filter((tool) => tool.annotations?.readOnlyHint === true).length;
    return { activeServers: servers.filter((server) => server.enabled).length, configuredTools, automaticTools };
  }, [selectedTools, servers, tools]);

  const add = async () => {
    try {
      await createMcpServer({ name, transport, command, url, args: args.split('\n').map((value) => value.trim()).filter(Boolean), allowed_tools: [] });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败');
    }
  };

  const discover = async (server: McpServer) => {
    try {
      const result = await discoverMcpTools(server.id);
      setTools((current) => ({ ...current, [server.id]: result.tools }));
      setSelectedTools((current) => ({ ...current, [server.id]: current[server.id] || server.allowed_tools }));
      setServers((current) => current.map((item) => item.id === server.id ? result.server : item));
      const recent = await listMcpEvents(server.id);
      setEvents((current) => ({ ...current, [server.id]: recent.events }));
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '连接检测失败');
    }
  };

  const remove = async (server: McpServer) => {
    if (!window.confirm(`删除 MCP 配置“${server.name}”？此操作不会删除服务文件。`)) return;
    try {
      await deleteMcpServer(server.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除失败');
    }
  };

  const toggleTool = (serverId: string, toolName: string) => setSelectedTools((current) => {
    const selected = current[serverId] || [];
    return { ...current, [serverId]: selected.includes(toolName) ? selected.filter((item) => item !== toolName) : [...selected, toolName] };
  });

  return (
    <section className="mcp-page" aria-label="MCP 连接中心">
      <header className="mcp-hero">
        <div>
          <span className="mcp-eyebrow">LOCAL TOOL GATEWAY</span>
          <h1>MCP 连接中心</h1>
          <p>集中管理本地 MCP 服务、工具授权与调用安全边界。</p>
        </div>
        <button className="mcp-primary-button" onClick={() => document.getElementById('mcp-add-service')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>添加服务</button>
      </header>

      {error && <div className="skills-error" role="alert">{error}</div>}

      <section className="mcp-overview" aria-label="连接总览">
        <div className="mcp-section-heading"><h2>连接总览</h2><span>实时配置状态</span></div>
        <div className="mcp-metrics">
          <Metric label="已启用服务" value={summary.activeServers} detail={`共 ${servers.length} 个已配置`} tone="accent" />
          <Metric label="已授权工具" value={summary.configuredTools} detail="可由主对话调用" tone="neutral" />
          <Metric label="自动执行工具" value={summary.automaticTools} detail="服务声明为只读" tone="success" />
        </div>
      </section>

      <section className="mcp-section" aria-label="服务配置">
        <div className="mcp-section-heading"><h2>服务配置</h2><span>每项服务独立检测与授权</span></div>
        {servers.length === 0 ? <EmptyServices onAdd={() => document.getElementById('mcp-add-service')?.scrollIntoView({ behavior: 'smooth', block: 'start' })} /> : (
          <div className="mcp-server-list">
            {servers.map((server) => <ServerPanel key={server.id} server={server} tools={tools[server.id] || []} selected={selectedTools[server.id] || []} events={events[server.id] || []}
              onToggleEnabled={() => void setMcpEnabled(server.id, !server.enabled).then(load).catch((reason) => setError(reason.message))}
              onDiscover={() => void discover(server)} onRemove={() => void remove(server)} onToggleTool={toggleTool}
              onUpdateServer={(updated) => setServers((current) => current.map((item) => item.id === updated.id ? updated : item))}
              onSelectAutomaticTools={(serverId, automaticTools) => setSelectedTools((current) => ({ ...current, [serverId]: automaticTools }))}
              onSaveTools={() => void setMcpAllowedTools(server.id, selectedTools[server.id] || []).then(load).catch((reason) => setError(reason.message))} />)}
          </div>
        )}
      </section>

      <section id="mcp-add-service" className="mcp-add-service" aria-label="添加 MCP 服务">
        <div className="mcp-section-heading"><div><h2>添加 MCP 服务</h2><span>支持本地 stdio 与远程 Streamable HTTP / SSE 响应</span></div></div>
        <div className="mcp-form-grid">
          <label>服务名称<input aria-label="服务名称" value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>连接方式<select aria-label="连接方式" value={transport} onChange={(event) => setTransport(event.target.value as 'stdio' | 'http')}><option value="stdio">本地 stdio</option><option value="http">远程 HTTP</option></select></label>
          {transport === 'stdio' ? <><label>启动命令<input aria-label="启动命令" value={command} onChange={(event) => setCommand(event.target.value)} /></label><label className="mcp-form-wide">命令参数 <small>每行一个参数</small><textarea aria-label="命令参数" value={args} onChange={(event) => setArgs(event.target.value)} /></label></> : <label className="mcp-form-wide">服务地址<input aria-label="MCP 服务地址" placeholder="https://example.com/mcp" value={url} onChange={(event) => setUrl(event.target.value)} /></label>}
        </div>
        <div className="mcp-form-foot"><span>保存后请启用服务，并执行一次连接检测。</span><button className="mcp-primary-button" onClick={() => void add()}>保存服务配置</button></div>
      </section>
    </section>
  );
}

function Metric({ label, value, detail, tone }: { label: string; value: number; detail: string; tone: string }) {
  return <article className={`mcp-metric mcp-metric-${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function EmptyServices({ onAdd }: { onAdd: () => void }) {
  return <div className="mcp-empty"><div className="mcp-empty-mark">⌘</div><h3>尚未接入 MCP 服务</h3><p>添加本地 stdio 服务后，即可检测工具并选择允许主对话调用的范围。</p><button className="mcp-secondary-button" onClick={onAdd}>添加第一个服务</button></div>;
}

function ServerPanel({ server, tools, selected, events, onToggleEnabled, onDiscover, onRemove, onToggleTool, onSelectAutomaticTools, onSaveTools, onUpdateServer }: {
  server: McpServer; tools: McpTool[]; selected: string[]; events: McpEvent[]; onToggleEnabled: () => void; onDiscover: () => void; onRemove: () => void; onToggleTool: (serverId: string, toolName: string) => void; onSelectAutomaticTools: (serverId: string, toolNames: string[]) => void; onSaveTools: () => void; onUpdateServer: (server: McpServer) => void;
}) {
  const automaticTools = tools.filter((tool) => tool.annotations?.readOnlyHint === true).map((tool) => tool.name);
  const connectedToolCount = server.enabled ? selected.length : 0;
  const isConnected = server.status === 'connected';
  const latestFailure = events.find((event) => !event.ok);
  const [editingEnvironment, setEditingEnvironment] = useState(false);
  const [editingHeaders, setEditingHeaders] = useState(false);
  const [editingTimeout, setEditingTimeout] = useState(false);
  const [environmentText, setEnvironmentText] = useState('');
  const [headersText, setHeadersText] = useState('');
  const [environmentError, setEnvironmentError] = useState('');
  const [timeoutText, setTimeoutText] = useState(String(server.timeout_seconds));

  const saveEnvironment = async () => {
    const environment: Record<string, string> = {};
    for (const line of environmentText.split('\n').map((item) => item.trim()).filter(Boolean)) {
      const separator = line.indexOf('=');
      if (separator <= 0) {
        setEnvironmentError('每行请使用 KEY=VALUE 格式');
        return;
      }
      environment[line.slice(0, separator).trim()] = line.slice(separator + 1);
    }
    try {
      const updated = await setMcpEnvironment(server.id, environment);
      onUpdateServer(updated);
      setEnvironmentText('');
      setEditingEnvironment(false);
      setEnvironmentError('');
    } catch (reason) {
      setEnvironmentError(reason instanceof Error ? reason.message : '环境变量保存失败');
    }
  };

  const saveTimeout = async () => {
    const timeoutSeconds = Number(timeoutText);
    if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 120) {
      setEnvironmentError('响应超时必须为 1 到 120 秒之间的整数');
      return;
    }
    try {
      onUpdateServer(await setMcpTimeout(server.id, timeoutSeconds));
      setEditingTimeout(false);
      setEnvironmentError('');
    } catch (reason) {
      setEnvironmentError(reason instanceof Error ? reason.message : '超时保存失败');
    }
  };

  const saveHeaders = async () => {
    const headers: Record<string, string> = {};
    for (const line of headersText.split('\n').map((item) => item.trim()).filter(Boolean)) {
      const separator = line.indexOf('=');
      if (separator <= 0) { setEnvironmentError('每行请使用 KEY=VALUE 格式'); return; }
      headers[line.slice(0, separator).trim()] = line.slice(separator + 1);
    }
    try {
      onUpdateServer(await setMcpHeaders(server.id, headers));
      setHeadersText(''); setEditingHeaders(false); setEnvironmentError('');
    } catch (reason) { setEnvironmentError(reason instanceof Error ? reason.message : '请求头保存失败'); }
  };

  return <article className="mcp-server-panel">
    <div className="mcp-server-topline">
      <div className={`mcp-server-icon ${server.enabled ? 'is-online' : ''}`}>⌘</div>
      <div className="mcp-server-identity"><div><h3>{server.name}</h3><span data-testid="mcp-session-state" data-status={server.status} className={`mcp-server-state ${server.enabled ? 'is-online' : ''}`}>{isConnected ? '已连接' : server.enabled ? '已启用' : '未启用'}</span></div><code>{server.transport === 'http' ? server.url : `${server.command} ${server.args.join(' ')}`}</code>{connectedToolCount > 0 && <span className="mcp-conversation-ready">已接入主对话 · {connectedToolCount} 个工具</span>}{server.env_keys.length > 0 && <span className="mcp-environment-summary">变量：{server.env_keys.join(' · ')}</span>}</div>
      <div className="mcp-server-actions"><button className="mcp-secondary-button" onClick={() => setEditingEnvironment((current) => !current)}>环境变量</button>{server.transport === 'http' && <button className="mcp-secondary-button" onClick={() => setEditingHeaders((current) => !current)}>请求头</button>}<button className="mcp-secondary-button" onClick={() => setEditingTimeout((current) => !current)}>超时 {server.timeout_seconds} 秒</button><button className="mcp-secondary-button" onClick={onToggleEnabled}>{server.enabled ? '停用' : '启用'}</button><button className="mcp-primary-button" disabled={!server.enabled} onClick={onDiscover}>{latestFailure ? '重新检测连接' : '检测连接'}</button><button className="mcp-icon-button" aria-label={`删除配置 ${server.name}`} onClick={onRemove}>×</button></div>
    </div>
    {editingEnvironment && <section className="mcp-environment-editor"><div><h4>环境变量</h4><span>仅此处输入值；保存后只显示变量名，并会重新建立连接。</span></div><textarea aria-label={`环境变量 ${server.name}`} value={environmentText} onChange={(event) => setEnvironmentText(event.target.value)} placeholder="SEARCH_API_KEY=...\nREGION=cn" />{server.env_keys.length > 0 && <div className="mcp-environment-keys">{server.env_keys.map((key) => <span key={key}>{key}</span>)}</div>}{environmentError && <p role="alert">{environmentError}</p>}<button className="mcp-primary-button" onClick={() => void saveEnvironment()}>保存环境变量</button></section>}
    {editingHeaders && <section className="mcp-environment-editor"><div><h4>认证请求头</h4><span>每行 KEY=VALUE；保存后仅显示键名，并会重新建立连接。</span></div><textarea aria-label={`请求头 ${server.name}`} value={headersText} onChange={(event) => setHeadersText(event.target.value)} placeholder="Authorization=Bearer ...\nX-API-Key=..." />{server.header_keys.length > 0 && <div className="mcp-environment-keys">{server.header_keys.map((key) => <span key={key}>{key}</span>)}</div>}{environmentError && <p role="alert">{environmentError}</p>}<button className="mcp-primary-button" onClick={() => void saveHeaders()}>保存请求头</button></section>}
    {editingTimeout && <section className="mcp-timeout-editor"><label>响应超时<input aria-label={`响应超时 ${server.name}`} type="number" min="1" max="120" value={timeoutText} onChange={(event) => setTimeoutText(event.target.value)} /> 秒</label><span>超时后会关闭当前连接；下次调用会自动重连。</span><button className="mcp-primary-button" onClick={() => void saveTimeout()}>保存超时</button></section>}
    <div className="mcp-server-body">
      <section className="mcp-permissions"><div className="mcp-panel-heading"><div><h4>工具权限</h4><span>{tools.length ? `已发现 ${tools.length} 个工具` : '请先检测连接以发现工具'}</span></div>{tools.length > 0 && <div className="mcp-permission-actions"><button className="mcp-text-button" disabled={!server.enabled || automaticTools.length === 0} onClick={() => onSelectAutomaticTools(server.id, automaticTools)}>选择全部可自动执行工具</button><button className="mcp-text-button" disabled={!server.enabled} onClick={onSaveTools}>保存授权</button></div>}</div>
        {tools.length > 0 ? <div className="mcp-tool-list">{tools.map((tool) => <label key={tool.name} className="mcp-tool-row"><input type="checkbox" checked={selected.includes(tool.name)} disabled={!server.enabled} onChange={() => onToggleTool(server.id, tool.name)} /><span className="mcp-tool-name">{tool.name}<small>{tool.description || 'MCP 工具'}</small></span><span className={`mcp-tool-safety ${tool.annotations?.readOnlyHint === true ? 'is-read-only' : 'requires-approval'}`}>{tool.annotations?.readOnlyHint === true ? '自动执行' : '需确认'}</span></label>)}</div> : <p className="mcp-panel-empty">检测仅执行初始化与工具发现，不会调用工具。</p>}
      </section>
      <section className="mcp-activity"><div className="mcp-panel-heading"><div><h4>最近活动</h4><span>不记录参数与结果</span></div></div>{latestFailure && <McpFailureGuide event={latestFailure} />}<McpStatus events={events} /></section>
    </div>
  </article>;
}

function McpFailureGuide({ event }: { event: McpEvent }) {
  const messages = {
    startup_failed: '无法启动 MCP 服务，请检查启动命令。',
    timeout: 'MCP 服务响应超时，请检查服务状态后重新检测。',
    protocol_error: 'MCP 服务返回了无效响应，请重新检测连接。',
    tool_error: 'MCP 工具执行失败，请确认页面状态后重试。',
    unknown: 'MCP 操作失败，请重新检测连接。',
  };
  return <p className="mcp-failure-guide" role="status">最近操作失败：{messages[event.failure_kind || 'unknown']}</p>;
}

function McpStatus({ events }: { events: McpEvent[] }) {
  const discovery = events.find((event) => event.kind === 'discovery');
  const call = events.find((event) => event.kind === 'tool_call');
  if (!discovery && !call) return <p className="mcp-panel-empty">暂无活动记录</p>;
  return <div className="mcp-activity-list">{discovery && <p><span className={discovery.ok ? 'mcp-event-dot success' : 'mcp-event-dot'} />连接检测 · {discovery.ok ? '成功' : '失败'} <small>{discovery.duration_ms}ms</small></p>}{call && <p><span className={call.ok ? 'mcp-event-dot success' : 'mcp-event-dot'} />{call.tool_name || '工具'} · {call.ok ? '调用成功' : '调用失败'} <small>{call.duration_ms}ms</small></p>}</div>;
}
