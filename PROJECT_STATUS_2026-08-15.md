# 项目状态（2026-08-15）

## 1. 已完成内容

当前工作位于分支 `feature/background-task-queue`，最近提交为 `094aa88 fix(聊天): 清理已删除会话的任务状态`。

### 任务中心与后台任务队列

- 任务中心支持 `queued` 状态，并限制其只能启动或进入终态；排队中任务不能错误更新进度或被当作运行中任务停止。
- 已实现私有 JSON 队列账本：`queue.json` 原子写入（临时文件、`fsync`、替换），并使用空的 `queue.lock` 完成 Windows 跨进程一字节文件锁。
- 队列作业仅持久化最小字段：`task_id`、`session_id`、`message`、`created_at`、`state`；不写入工具参数、工具输出、模型原文或原始异常。
- 已实现单工作线程 FIFO 调度，支持工具审批暂停/继续、queued/awaiting/running 三类取消、应用重启恢复、账本或任务中心瞬时故障隔离，以及 stop 后立即 start 的可靠衔接。
- 崩溃恢复已覆盖：未实际启动的作业恢复为 `queued`；已运行或等待审批的作业被标记为“服务重启，执行未完成”；孤立的旧队列任务会被安全补偿。

### 应用与 API 集成

- 新增 `TaskQueueSettings`，默认目录为 `data/task_queue`，并接入 YAML 配置、应用服务装配及服务启动/关闭生命周期。
- 已提供后台任务接口：
  - `POST /api/tasks`：创建后台任务，返回 `202`。
  - `GET /api/tasks`、`GET /api/tasks/{task_id}`：读取任务及排队位置。
  - `DELETE /api/tasks/{task_id}`：取消任务。
  - `POST /api/tasks/{task_id}/tool-approvals/{call_id}`：处理工具审批。
- 旧的 `/api/chat/stream` 与原有会话审批路由保持兼容。
- 队列账本不可用时，读取接口返回安全的 `503` / `task_queue_unavailable`，不会返回账本路径、原始异常或用户消息。
- 后台排队任务在任务中心/API 中只显示固定摘要“后台任务”；历史 `request_queued` 记录会在初始化时迁移脱敏，原消息只保留在私有队列账本中。

### 前端接入

- 聊天发送已接入 `POST /api/tasks`，不再依赖流式接口完成后台任务提交。
- 已实现 1 秒任务详情轮询、排队位置、queued/running/awaiting 状态展示、取消任务、完成后会话回填，以及 failed/stopped/503 的安全提示。
- 工具审批仅在服务端返回安全 `approval_call_id` 时显示批准/拒绝按钮；审批提交期间按钮禁用并使用单飞保护防止重复提交。
- 已处理会话切换、新建聊天、删除会话和组件卸载时的轮询生命周期；活动任务元数据按会话保留，切回后会重新读取并恢复展示与控制。

### 验证记录

- Task 4（后端 API）最后一次完整后端验证：`315 passed, 3 skipped`。
- 审批标识补充后后端验证：`316 passed, 3 skipped`。
- Task 5 前端最近一次完整验证（在最后一项删除会话修复之前）：`106/106` 测试通过，`npm run build` 通过。
- 最新提交 `094aa88` 已补充“删除当前会话后停止轮询、清理任务状态”回归测试；它尚待 Task 5 的最终规格与质量复审重新确认。

## 2. 当前代码结构

```text
iris_agent/
├── task_center/
│   ├── models.py          # AgentTask、事件与公开任务状态
│   └── service.py         # 任务状态机、恢复、历史队列摘要迁移
├── task_queue/
│   ├── models.py          # QueueJob（五字段、queued/active）
│   ├── repository.py      # JSON 账本、原子写、Windows 文件锁
│   └── service.py         # 单 worker、审批、取消、恢复、生命周期
├── api/
│   ├── app.py             # FastAPI 装配与队列依赖注入
│   └── tasks_api.py       # 后台任务 REST API 与安全错误映射
├── config/                # TaskQueueSettings 及 YAML 配置接入
└── bootstrap.py           # ApplicationServices / 队列服务构造

tests/
├── task_center/           # 状态机、恢复、摘要迁移测试
├── task_queue/            # 账本、并发、取消、恢复、worker 测试
└── api/                   # 任务 API、配置与应用装配测试

web-react/src/
├── hooks/useChat.ts       # 后台提交、轮询、跨会话任务状态
├── api/                   # 任务 API 客户端
├── components/ChatContainer.tsx  # 状态、取消、审批 UI
└── App.tsx                # Hook 状态向界面传递
```

## 3. 关键参数

| 参数 | 当前值 / 规则 |
| --- | --- |
| 队列目录 | `data/task_queue` |
| 账本文件 | `data/task_queue/queue.json` |
| 锁文件 | `data/task_queue/queue.lock`，仅 Windows 一字节文件锁，不保存业务数据 |
| 队列并发 | 单工作线程，最大并发执行数为 1 |
| 调度顺序 | FIFO |
| 队列状态 | `queued`、`active` |
| 任务关键状态 | `queued`、`running`、`awaiting_approval` 及终态 |
| 轮询间隔 | 前端 1 秒 |
| 审批标识 | 仅 `awaiting_approval` 任务返回 `approval_call_id` |
| 队列不可用响应 | HTTP `503`，`task_queue_unavailable` |
| 登录/鉴权 | 当前明确暂缓，尚未实现 |

## 4. 未解决问题

### 已解决（2026-08-15 收尾）

- `094aa88` 的规格与质量复审：通过，Task 5 正式收尾。
- Task 6：任务中心页面的队列位置/取消入口已实现并全量验证。
- `feature/background-task-queue` 已推送并 fast-forward 合并到 `main`（提交 `a62d059`）。

### 产品范围中明确暂缓

- 登录、鉴权及用户隔离。

## 5. 下一步建议

- 后台任务队列一期已全部完成并合并到 `main`。
- 后续若恢复登录开发，再将队列目录、任务读取与取消/审批操作接入用户级授权与隔离。
