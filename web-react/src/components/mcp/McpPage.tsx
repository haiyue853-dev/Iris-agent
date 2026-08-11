import { useEffect, useState } from 'react';
import { createMcpServer, listMcpServers, setMcpEnabled, type McpServer } from '../../api/mcp';

export default function McpPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('Browser MCP');
  const [command, setCommand] = useState('node');
  const [args, setArgs] = useState('D:/agent/browser-mcp/browser-mcp-server-v2.js');
  const [error, setError] = useState('');
  const load = () => listMcpServers().then((value) => setServers(value.servers)).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const add = async () => { try { await createMcpServer({ name, command, args: args ? args.split('\n').map((v) => v.trim()).filter(Boolean) : [], allowed_tools: [] }); load(); } catch (err) { setError(err instanceof Error ? err.message : '保存失败'); } };
  return <section className="skills-page" aria-label="MCP 连接中心"><div className="skills-page-head"><h1 className="skills-page-title">MCP 连接中心</h1><p className="skills-page-desc">配置本地 MCP 服务；启用仅代表允许 Iris 使用，外部命令不会自动启动。</p></div>{error && <div className="skills-error" role="alert">{error}</div>}<div className="skills-grid">{servers.map((server) => <article className="skill-card" key={server.id}><h2>{server.name}</h2><p>{server.command} {server.args.join(' ')}</p><button className="skill-card-toggle" onClick={() => setMcpEnabled(server.id, !server.enabled).then(load)}>{server.enabled ? '停用' : '启用'}</button></article>)}</div><div className="skills-page-head"><h2>添加本地 stdio 服务</h2><input value={name} onChange={(e) => setName(e.target.value)} /><input value={command} onChange={(e) => setCommand(e.target.value)} /><textarea value={args} onChange={(e) => setArgs(e.target.value)} /><button className="uml-generate-btn" onClick={() => void add()}>保存 MCP 配置</button></div></section>;
}
