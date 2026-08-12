# MCP 运行时工具刷新实现计划

**目标：** MCP 配置变更后立即刷新主对话可用的 MCP 工具。

### 任务 1：安全替换 MCP 工具

- 修改 `iris_agent/tools/registry.py`、`iris_agent/mcp_center/tools.py`
- 测试 `tests/mcp/test_runtime.py`

- [ ] 先写测试：替换 `mcp__` 工具保留内置工具，发现失败保持旧 MCP 工具。
- [ ] 为注册表加入 `remove_prefix()` 和工具复制接口；实现 `McpToolRefresher.refresh()` 的临时构建与原子替换。
- [ ] 运行 `pytest tests/mcp/test_runtime.py -v`。

### 任务 2：管理 API 触发刷新

- 修改 `iris_agent/bootstrap.py`、`iris_agent/api/mcp_api.py`
- 测试 `tests/api/test_mcp_api.py`

- [ ] 先写 API 测试：启停、白名单变更和删除后调用刷新器。
- [ ] 将刷新器注入 MCP 路由并在成功配置变更后调用。
- [ ] 运行 MCP API 与启动装配测试。
