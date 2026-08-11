# MCP 管理操作实现计划

**目标：** 让用户可检测 MCP 服务连接并删除本地配置，而不调用 MCP 工具或修改服务文件。

**架构：** 复用已有 `discover_tools()` 作为连接检测；服务层负责原子删除配置，API 暴露 DELETE 路由，前端使用现有 MCP 卡片与主题按钮。

### 任务 1：删除服务配置

- 修改 `iris_agent/mcp_center/service.py`
- 测试 `tests/mcp/test_mcp_center_service.py`

- [ ] 编写删除后列表为空、配置文件同步更新的失败测试。
- [ ] 实现 `delete(server_id)`：读取目标、从内存字典移除、调用 `_save()`、返回删除的服务。
- [ ] 运行 `pytest tests/mcp/test_mcp_center_service.py -v`。

### 任务 2：删除与连接检测 API

- 修改 `iris_agent/api/mcp_api.py`
- 测试 `tests/api/test_mcp_api.py`

- [ ] 编写 DELETE 成功返回 204、未知服务返回 404 的失败测试。
- [ ] 添加 `DELETE /api/mcp/servers/{server_id}`，复用现有稳定错误格式。
- [ ] 运行对应 API 测试。

### 任务 3：管理页操作

- 修改 `web-react/src/api/mcp.ts`、`web-react/src/components/mcp/McpPage.tsx`、`web-react/src/App.css`
- 测试 `web-react/src/components/mcp/McpPage.test.tsx`

- [ ] 编写测试，断言“检测连接”调用 discover 路由、“删除”调用 DELETE 并刷新列表。
- [ ] 复用发现请求作为检测，显示成功或失败反馈；删除操作仅删除配置并刷新卡片。
- [ ] 运行 Vitest、TypeScript 检查与前端生产构建。
