# MCP 工具调用链实现计划

> **面向 AI 代理的工作者：** 必须使用 `executing-plans` 逐任务实施并记录验证。

**目标：** 将已启用且被允许的 MCP 工具安全接入主对话，并为写操作提供确认界面。

**架构：** `McpCenterService` 管理 JSON-RPC 进程生命周期与工具适配；`ToolRegistry` 承载命名空间化工具；Agent 通过可恢复的等待状态发出确认事件，API 和前端沿用 NDJSON 流继续会话。

## 文件结构

- 修改 `iris_agent/mcp_center/service.py`：工具描述发现、受控调用、进程超时与白名单检查。
- 新建 `iris_agent/mcp_center/tools.py`：将 MCP 描述转为 `Tool`，标记只读/待确认工具。
- 修改 `iris_agent/core/agent.py`：暂停与恢复写工具调用。
- 修改 `iris_agent/bootstrap.py`：启动时注册 MCP 工具。
- 修改 `iris_agent/api/app.py`、`iris_agent/api/mcp_api.py`：确认/拒绝 API 与 NDJSON 续流。
- 修改 `web-react/src/types.ts`、`api/chat.ts`、`hooks/useChat.ts`、聊天组件：确认事件和操作卡片。
- 新建 `tests/mcp/test_runtime.py`、`tests/core/test_mcp_approval.py` 与对应前端测试。

### 任务 1：MCP JSON-RPC 运行时与工具适配

- [ ] 先在 `tests/mcp/test_runtime.py` 写失败测试：模拟 stdio 服务，断言仅启用且白名单允许的工具被命名为 `mcp__<server_id>__<name>`，并断言 `tools/call` 接收原名和 arguments。
- [ ] 运行 `..\\.venv\\Scripts\\python.exe -m pytest tests/mcp/test_runtime.py -v`，预期因缺少运行时适配失败。
- [ ] 在 `service.py` 提取初始化/读取响应/终止逻辑，加入 `discover_enabled_tools()` 和 `call_tool()`；在 `tools.py` 生成 schema 保真的 `Tool` 并将 MCP 错误转为 `ToolInvocationError`。
- [ ] 重跑该测试，预期通过；提交 `feat: execute allowed MCP tools`。

### 任务 2：启动注册和只读端到端 Agent 调用

- [ ] 在 `tests/test_bootstrap_services.py` 与 `tests/core/test_agent_loop.py` 写失败测试，验证启动时注册工具，模型调用只读 MCP 工具后接收结果并继续输出。
- [ ] 运行上述测试，预期缺少注册而失败。
- [ ] 修改 `bootstrap.py` 在创建 loop 前注册可发现工具；发现单服务失败时跳过而不阻断启动。
- [ ] 重跑测试并提交 `feat: register MCP tools in agent`。

### 任务 3：写操作确认与会话恢复

- [ ] 在 `tests/core/test_mcp_approval.py` 写失败测试：写工具发出 `tool_approval_requested` 且未调用 MCP；批准后执行并继续；拒绝后把拒绝结果交给模型；重复/跨会话确认失败。
- [ ] 运行测试，预期 Agent 尚无暂停状态而失败。
- [ ] 在 `AgentService` 保存受会话和 call ID 绑定的挂起调用，新增 `approve_tool_call` / `reject_tool_call`；API 暴露确认端点并输出续流 NDJSON。
- [ ] 重跑测试并提交 `feat: require approval for MCP writes`。

### 任务 4：聊天确认卡片与回归验证

- [ ] 先写前端测试，模拟确认事件，断言展示服务名、工具名、JSON 参数，批准/拒绝请求正确并消费续流。
- [ ] 运行对应 Vitest，预期缺少确认状态和 UI 而失败。
- [ ] 扩展 `AgentEvent`、`api/chat.ts` 与 `useChat`，添加确认 API 和确认卡片；将其放入现有聊天流。
- [ ] 运行前端完整测试、构建和完整 Python 测试；使用 Browser MCP 只读工具做一次端到端验证；提交 `feat: approve MCP tool calls in chat`。
