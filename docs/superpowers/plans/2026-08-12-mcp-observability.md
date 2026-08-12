# MCP 可观测性实现计划

**目标：** 展示无敏感内容的 MCP 检测与调用最近状态。

### 任务 1：内存事件日志

- 修改 `iris_agent/mcp_center/service.py`
- 测试 `tests/mcp/test_mcp_center_service.py`

- [ ] 编写失败测试，断言检测事件不包含参数、响应或错误文本。
- [ ] 增加最多 50 条的事件环形列表，并在检测与调用结束时记录结果和耗时。
- [ ] 运行 MCP 服务测试。

### 任务 2：状态 API

- 修改 `iris_agent/api/mcp_api.py`
- 测试 `tests/api/test_mcp_api.py`

- [ ] 编写 GET 日志 API 失败测试。
- [ ] 增加 `GET /api/mcp/servers/{id}/events`。
- [ ] 运行 API 测试。

### 任务 3：管理页摘要

- 修改 `web-react/src/api/mcp.ts`、`web-react/src/components/mcp/McpPage.tsx`
- 测试 `web-react/src/components/mcp/McpPage.test.tsx`

- [ ] 编写页面测试，断言最近检测状态显示且不渲染敏感字段。
- [ ] 加载并渲染最近状态，复用现有卡片主题。
- [ ] 运行 Vitest、TypeScript 和生产构建。
