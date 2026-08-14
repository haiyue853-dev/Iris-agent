# MCP 失败提示与重新检测实现计划

> **面向 AI 代理的工作者：** 必须使用 `executing-plans` 逐项实现并记录验证。

**目标：** 为 MCP 失败事件提供安全分类，并在连接中心给出固定的恢复指引和重新检测入口。

**架构：** `McpCenterService` 将受控异常映射为有限的失败分类并随现有事件持久化；API 原样返回安全事件；React 卡片基于最新失败事件渲染固定说明和既有发现操作。

**技术栈：** Python、FastAPI、React、TypeScript、Vitest、pytest。

---

### 任务 1：安全失败分类持久化

**文件：**
- 修改：`iris_agent/mcp_center/service.py`
- 测试：`tests/mcp/test_mcp_center_service.py`

- [x] 步骤 1：新增失败测试，断言缺失启动命令产生 `startup_failed`，事件不包含原始错误。

```python
assert service.events(server.id)[0]["failure_kind"] == "startup_failed"
assert "error" not in service.events(server.id)[0]
```

- [x] 步骤 2：运行 `& .venv\Scripts\python.exe -m pytest tests/mcp/test_mcp_center_service.py -q`，确认新断言失败。
- [x] 步骤 3：给 `_record_event()` 添加可选 `failure_kind`，在发现与工具调用的受控异常路径传入固定分类；加载事件时只接受允许的分类。
- [x] 步骤 4：重新运行该 MCP 服务测试，确认通过（18 passed）。
- [x] 步骤 5：已提交 `4fb3c71 feat: 记录 MCP 安全失败分类`。

### 任务 2：连接中心失败提示

**文件：**
- 修改：`web-react/src/api/mcp.ts`
- 修改：`web-react/src/components/mcp/McpPage.tsx`
- 修改：`web-react/src/App.css`
- 测试：`web-react/src/components/mcp/McpPage.test.tsx`

- [x] 步骤 1：新增页面失败事件测试，断言只显示固定“启动失败”摘要与“重新检测连接”，不渲染事件中的任意敏感字段。

```tsx
expect(await screen.findByText('无法启动 MCP 服务，请检查启动命令。')).toBeInTheDocument();
expect(screen.queryByText('top-secret')).not.toBeInTheDocument();
```

- [x] 步骤 2：运行 Vitest，确认新增测试失败。
- [x] 步骤 3：扩展 `McpEvent` 类型，按 `failure_kind` 映射固定中文说明；卡片展示警示区，检测按钮根据失败状态显示“重新检测连接”。
- [x] 步骤 4：为警示区添加与现有 MCP 主题一致的弱警告色和移动端布局样式。
- [x] 步骤 5：重跑页面测试，确认通过；点击重新检测后以接口返回的事件刷新状态。
- [x] 步骤 6：已提交 `64f30a4 feat: 提示 MCP 失败并支持重新检测`。

### 任务 3：回归验证

**文件：**
- 无生产代码变更。

- [x] 步骤 1：运行后端全量测试：`221 passed, 3 skipped`。
- [x] 步骤 2：MCP 页面 Vitest：`8 passed`。
- [x] 步骤 3：生产构建通过；仅保留既有 Mermaid 大 chunk 警告。
- [x] 步骤 4：`git diff --check` 通过；仅提交本计划涉及的文件。
