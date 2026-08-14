# Agent 任务中心一期实现计划

> **面向 AI 代理的工作者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框语法跟踪。

**目标：** 为每次主聊天 Agent 执行持久化安全任务时间线，提供只读 API、NDJSON 任务标识与可跳转的前端任务中心。

**架构：** 新增 `task_center` 领域模块负责原子 JSON 账本、状态流转和安全事件裁剪；API 层在流式聊天和审批流旁路映射任务事件；前端仅通过任务 API 获取摘要和详情。

**技术栈：** Python/FastAPI/pytest、React/TypeScript/Vitest。

---

## 文件结构

- 创建 `iris_agent/task_center/models.py`：任务、事件及安全序列化模型。
- 创建 `iris_agent/task_center/repository.py`：原子 JSON 账本与保留上限。
- 创建 `iris_agent/task_center/service.py`：状态转换、事件映射和重启收尾。
- 创建 `iris_agent/api/tasks_api.py`：任务摘要、详情 API。
- 修改 `iris_agent/config/settings.py`、`iris_agent/bootstrap.py`、`server.py`、`iris_agent/api/app.py`：配置、依赖注入、流旁路和 API 注册。
- 创建 `tests/task_center/test_service.py`、`tests/api/test_tasks_api.py`：账本、敏感数据排除、流、审批和 API 覆盖。
- 创建 `web-react/src/api/tasks.ts`、`web-react/src/components/tasks/TaskCenterPage.tsx`、相应测试：客户端与列表/时间线视图。
- 修改 `web-react/src/types.ts`、`web-react/src/hooks/useChat.ts`、`web-react/src/components/ChatContainer.tsx`、`web-react/src/components/Sidebar.tsx`、`web-react/src/App.tsx`、`web-react/src/App.css`：任务跳转、导航和样式。

## 任务 1：任务账本与状态服务

- [x] 编写失败测试，覆盖创建、工具/审批/完成/失败/中断、100 项裁剪、重启恢复和账本不含参数/结果/异常/回复正文。
- [x] 运行 `pytest tests/task_center/test_service.py -v`，确认失败。
- [x] 实现模型、原子 JSON 仓储和服务。
- [x] 运行同一测试文件，确认通过。
- [x] 提交 `feat: add task center ledger`。

## 任务 2：聊天流、审批流和只读 API

- [x] 编写失败 API 测试，覆盖 `task_started` 首事件、事件旁路、审批关联、列表过滤/上限、详情和稳定 404。
- [x] 运行 `pytest tests/api/test_tasks_api.py -v`，确认失败。
- [x] 注入任务中心，注册路由，给生成器添加 `GeneratorExit`/异常状态并映射安全事件。
- [x] 运行 API 测试及 `pytest tests/api/test_app.py -v`，确认通过。
- [x] 提交 `feat: expose task center APIs`。

## 任务 3：任务中心前端与聊天跳转

- [x] 编写失败 Vitest 测试，覆盖侧栏入口、列表和时间线、加载失败重试、`task_started` 后的查看任务跳转，且不渲染未知敏感字段。
- [x] 运行 `npm test -- --runInBand`（或对应任务测试），确认失败。
- [x] 实现任务 API、类型、任务页面、导航、聊天状态和跳转入口。
- [x] 运行前端测试与 `npm run build`，确认通过。
- [x] 提交 `feat: add task center workspace`。

## 任务 4：全量验证

- [x] 运行 `pytest -q`。
- [x] 运行 `npm test` 与 `npm run build`。
- [x] 检查 `git status --short`，仅保留任务中心相关变更。
