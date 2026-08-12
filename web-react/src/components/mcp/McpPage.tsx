import { useEffect, useState } from 'react';

import {
  createMcpServer,
  deleteMcpServer,
  discoverMcpTools,
  listMcpEvents,
  listMcpServers,
  setMcpAllowedTools,
  setMcpEnabled,
  type McpServer,
  type McpEvent,
} from '../../api/mcp';

type McpTool = { name: string; description?: string };

export default function McpPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('Browser MCP');
  const [command, setCommand] = useState('node');
  const [args, setArgs] = useState('D:/agent/browser-mcp/browser-mcp-server-v2.js');
  const [error, setError] = useState('');
  const [tools, setTools] = useState<Record<string, McpTool[]>>({});
  const [selectedTools, setSelectedTools] = useState<Record<string, string[]>>({});
  const [events, setEvents] = useState<Record<string, McpEvent[]>>({});

  const load = async () => {
    try {
      const loaded = (await listMcpServers()).servers;
      setServers(loaded);
      const entries = await Promise.all(loaded.map(async (server) => [server.id, (await listMcpEvents(server.id)).events] as const));
      setEvents(Object.fromEntries(entries));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法加载 MCP 配置');
    }
  };

  useEffect(() => { void load(); }, []);

  const add = async () => {
    try {
      await createMcpServer({
        name,
        command,
        args: args.split('\n').map((value) => value.trim()).filter(Boolean),
        allowed_tools: [],
      });
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
      setError('');
      const recent = await listMcpEvents(server.id);
      setEvents((current) => ({ ...current, [server.id]: recent.events }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '连接检测失败');
    }
  };

  const remove = async (server: McpServer) => {
    if (!window.confirm(`删除 MCP 配置“${server.name}”？此操作不会删除服务文件。`)) return;
    try {
      await deleteMcpServer(server.id);
      setTools((current) => { const next = { ...current }; delete next[server.id]; return next; });
      setSelectedTools((current) => { const next = { ...current }; delete next[server.id]; return next; });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除失败');
    }
  };

  const toggleTool = (serverId: string, toolName: string) => {
    setSelectedTools((current) => {
      const selected = current[serverId] || [];
      return {
        ...current,
        [serverId]: selected.includes(toolName) ? selected.filter((name) => name !== toolName) : [...selected, toolName],
      };
    });
  };

  return (
    <section className="skills-page" aria-label="MCP 连接中心">
      <div className="skills-page-head">
        <h1 className="skills-page-title">MCP 连接中心</h1>
        <p className="skills-page-desc">配置本地 MCP 服务，检测连接后选择允许主对话调用的工具。</p>
      </div>
      {error && <div className="skills-error" role="alert">{error}</div>}
      <div className="skills-grid">
        {servers.map((server) => (
          <article className="skill-card" key={server.id}>
            <h2>{server.name}</h2>
            <p>{server.command} {server.args.join(' ')}</p>
            <div className="skill-card-actions">
              <button className="skill-card-toggle" onClick={() => void setMcpEnabled(server.id, !server.enabled).then(load)}>
                {server.enabled ? '停用' : '启用'}
              </button>
              <button className="skill-card-open" disabled={!server.enabled} onClick={() => void discover(server)}>检测连接</button>
              <button className="skill-card-action" aria-label={`删除配置 ${server.name}`} onClick={() => void remove(server)}>删除配置</button>
            </div>
            <McpStatus events={events[server.id] || []} />
            {tools[server.id]?.map((tool) => (
              <label key={tool.name} className="mcp-tool-option">
                <input type="checkbox" checked={(selectedTools[server.id] || []).includes(tool.name)} disabled={!server.enabled} onChange={() => toggleTool(server.id, tool.name)} />
                {tool.name}
              </label>
            ))}
            {tools[server.id] && (
              <button className="skill-card-action" disabled={!server.enabled} onClick={() => void setMcpAllowedTools(server.id, selectedTools[server.id] || []).then(load).catch((reason) => setError(reason.message))}>保存白名单</button>
            )}
          </article>
        ))}
      </div>
      <div className="skills-page-head">
        <h2>添加本地 stdio 服务</h2>
        <input aria-label="服务名称" value={name} onChange={(event) => setName(event.target.value)} />
        <input aria-label="启动命令" value={command} onChange={(event) => setCommand(event.target.value)} />
        <textarea aria-label="命令参数" value={args} onChange={(event) => setArgs(event.target.value)} />
        <button className="uml-generate-btn" onClick={() => void add()}>保存 MCP 配置</button>
      </div>
    </section>
  );
}

function McpStatus({ events }: { events: McpEvent[] }) {
  const discovery = events.find((event) => event.kind === 'discovery');
  const call = events.find((event) => event.kind === 'tool_call');
  if (!discovery && !call) return <p className="mcp-status">暂无最近状态</p>;
  return (
    <div className="mcp-status" aria-label="最近 MCP 状态">
      {discovery && <p>最近检测：{discovery.ok ? '成功' : '失败'} · {discovery.duration_ms}ms</p>}
      {call && <p>最近调用：{call.tool_name || '工具'} · {call.ok ? '成功' : '失败'} · {call.duration_ms}ms</p>}
    </div>
  );
}
