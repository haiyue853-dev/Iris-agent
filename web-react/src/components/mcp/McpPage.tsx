import { useEffect, useState } from 'react';
import { createMcpServer, discoverMcpTools, listMcpServers, setMcpAllowedTools, setMcpEnabled, type McpServer } from '../../api/mcp';

export default function McpPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('Browser MCP');
  const [command, setCommand] = useState('node');
  const [args, setArgs] = useState('D:/agent/browser-mcp/browser-mcp-server-v2.js');
  const [error, setError] = useState('');
  const [tools, setTools] = useState<Record<string, { name: string; description?: string }[]>>({});
  const [selectedTools, setSelectedTools] = useState<Record<string, string[]>>({});
  const load = () => listMcpServers().then((value) => setServers(value.servers)).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const add = async () => { try { await createMcpServer({ name, command, args: args ? args.split('\n').map((v) => v.trim()).filter(Boolean) : [], allowed_tools: [] }); load(); } catch (err) { setError(err instanceof Error ? err.message : '保存失败'); } };
  const discover = async (server: McpServer) => { try { const value = await discoverMcpTools(server.id); setTools((current) => ({ ...current, [server.id]: value.tools })); setSelectedTools((current) => ({ ...current, [server.id]: current[server.id] || server.allowed_tools })); } catch (err) { setError(err instanceof Error ? err.message : '发现失败'); } };
  return <section className="skills-page" aria-label="MCP 连接中心"><div className="skills-page-head"><h1 className="skills-page-title">MCP 连接中心</h1><p className="skills-page-desc">配置本地 MCP 服务；发现后勾选允许主对话调用的工具。</p></div>{error && <div className="skills-error" role="alert">{error}</div>}<div className="skills-grid">{servers.map((server) => <article className="skill-card" key={server.id}><h2>{server.name}</h2><p>{server.command} {server.args.join(' ')}</p><button className="skill-card-toggle" onClick={() => setMcpEnabled(server.id, !server.enabled).then(load)}>{server.enabled ? '停用' : '启用'}</button><button className="skill-card-open" disabled={!server.enabled} onClick={() => void discover(server)}>发现工具</button>{tools[server.id]?.map((tool) => <label key={tool.name} className="mcp-tool-option"><input type="checkbox" checked={(selectedTools[server.id] || []).includes(tool.name)} disabled={!server.enabled} onChange={() => setSelectedTools((current) => ({ ...current, [server.id]: (current[server.id] || []).includes(tool.name) ? current[server.id].filter((name) => name !== tool.name) : [...(current[server.id] || []), tool.name] }))} />{tool.name}</label>)}{tools[server.id] && <button className="skill-card-action" disabled={!server.enabled} onClick={() => setMcpAllowedTools(server.id, selectedTools[server.id] || []).then(load).catch((err) => setError(err.message))}>保存白名单</button>}</article>)}</div><div className="skills-page-head"><h2>添加本地 stdio 服务</h2><input value={name} onChange={(e) => setName(e.target.value)} /><input value={command} onChange={(e) => setCommand(e.target.value)} /><textarea value={args} onChange={(e) => setArgs(e.target.value)} /><button className="uml-generate-btn" onClick={() => void add()}>保存 MCP 配置</button></div></section>;
}
