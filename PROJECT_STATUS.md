# Iris Agent 项目状态

更新时间：2026-08-13  
当前分支：`main`  
最新提交：`e967240 docs: 规划 Agent 任务中心`

## 1. 已完成内容

### 主对话 Agent

- 支持 OpenAI 兼容接口与 DeepSeek 等模型配置。
- 已实现 NDJSON 流式对话、会话创建、切换、删除、重置和 JSON 持久化。
- 内置只读工具：当前时间、工作区目录列表、UTF-8 文本读取。
- 支持工具调用生命周期；危险工具需要在聊天界面人工批准，批准或拒绝后可继续对话。

### MCP 连接中心

- 支持本地 `stdio` MCP 服务的创建、启停、删除、工具发现、白名单、环境变量键名和超时配置。
- 已发现并获准的工具会注册到主 `ToolRegistry`，命名格式为 `mcp__<server_id>__<tool_name>`。
- MCP 使用持久 `stdio` 会话；停用、配置变化、超时或异常后会安全关闭，并在下次调用时重连。
- 前端提供服务状态、已授权工具、只读自动执行标记、近期活动、失败原因安全摘要及重新检测入口。
- 安全活动只记录服务 ID、事件类别、工具名、结果、耗时和时间；不记录工具参数、返回值、环境变量值或原始错误内容。

### AI 日报与附件

- AI 日报支持手工编辑、AI 修订、版本恢复、日报内聊天和 Markdown 下载。
- 支持 TXT、Markdown、DOCX、PDF、XLSX、XLS 附件提取及容量限制。
- 图片 OCR 属于可选本机能力，未配置时会安全标记为不可提取，不影响其他附件流程。

### UML 工作台

- UML 页面已收敛为 Draw.io 单一专业画布，支持持续编辑及 PNG、SVG、XML 导出。
- 已彻底移除 React Flow、Mermaid 及其旧画布组件、样式与前端依赖，避免重复画布和大包警告。

### 热点雷达与自动化

- 支持关键词订阅、热点扫描、去重、定时调度、手动执行、执行历史和失败来源追踪。
- 新热点会生成站内通知；通知支持已读、删除并关联热点条目。
- 自动化页面展示订阅、例行任务、未读通知、最近执行记录与热点结果。
- 服务启动时自动启动内置调度器；遗留的运行中自动化执行会被标记为未知状态，不会假装已完成。

### 前端与质量

- React 前端已统一主要工作台的导航和 Iris 主题风格。
- 最新一次完整前端验证：19 个测试文件、84 项测试通过；TypeScript 构建检查和生产构建通过。
- 后端最近记录的完整验证为 `221 passed, 3 skipped`；MCP、审批、持久会话、安全活动、自动化与通知均有自动化测试覆盖。

## 2. 当前代码结构

```text
iris-agent/
├── iris_agent/
│   ├── api/                 FastAPI 应用、路由与请求模型
│   ├── config/              YAML 与环境变量配置加载
│   ├── core/                AgentLoop、事件、消息、审批流程
│   ├── sessions/            会话模型与 JSON 仓储
│   ├── tools/               内置工具与 ToolRegistry
│   ├── mcp_center/          MCP 配置、stdio 会话、工具适配与安全活动
│   ├── reports/             日报、版本、附件、提取与日报聊天
│   ├── hot_radar/           热点订阅、扫描与去重
│   ├── automation/          定时任务、执行账本与调度器
│   ├── notifications/       站内通知存储与服务
│   └── skill_center/        内置 Skill 目录与启用状态
├── web-react/src/
│   ├── components/          聊天、MCP、日报、UML、自动化等页面组件
│   ├── api/                 前端 API 客户端
│   ├── hooks/               对话等状态逻辑
│   ├── App.tsx              视图路由与跨页面协调
│   ├── types.ts             前端领域类型
│   └── App.css              全局主题与页面样式
├── tests/                   后端单元、API 与集成测试
├── data/                    运行期 JSON 数据（会话、日报、MCP 等）
├── docs/superpowers/specs/  已确认的功能设计规格
├── server.py                FastAPI 启动入口与调度器生命周期
├── agent.yaml               本地配置
└── PROJECT_STATUS.md        本文档
```

## 3. 关键参数

| 分类 | 参数 | 默认值 / 约束 |
| --- | --- | --- |
| 模型 | `llm.model` | `deepseek-chat` |
| 模型 | `llm.base_url` | `https://api.deepseek.com/v1` |
| 模型 | `llm.temperature` | `0.2` |
| 模型 | `llm.timeout_seconds` | `60` 秒 |
| Agent | `agent.max_tool_rounds` | `8`，必须大于 `0` |
| 会话 | `sessions.directory` | `data/sessions` |
| 工具 | `tools.workspace_root` | `workspace` |
| 工具 | `tools.max_read_chars` | `20,000` 字符 |
| 日报 | `reports.max_input_chars` | `50,000` 字符 |
| 日报 | `reports.max_revision_chars` | `2,000` 字符 |
| 日报 | `reports.max_versions` | `20` 个版本 |
| 附件 | 单文件 / 总量 / 数量 | `10 MB` / `50 MB` / `10` 个 |
| 附件 | `reports.max_attachment_text_chars` | `20,000` 字符 |
| MCP | 单服务 `timeout_seconds` | 默认 `10` 秒，允许 `1–120` 秒 |
| MCP | 最近安全活动 | 最多保留 `50` 条 |
| 雷达 | `hot_radar.poll_interval_seconds` | `60` 秒，必须大于 `0` |
| 自动化 | 调度检查周期 | 服务内每 `15` 秒检查一次 |
| 服务 | HTTP 端口 | `8000` |
| 前端 | 开发端口 | Vite 默认 `5173` |

配置来源优先级：运行时覆盖参数、环境变量（如 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL`）优先于 `agent.yaml`，未配置时使用代码默认值。

## 4. 未解决问题

1. **任务中心尚未实现。** 已完成并提交设计规格，但尚未创建后端任务账本、只读 API、前端页面或聊天跳转。
2. **MCP 活动不是长期审计日志。** 当前仅保留最近 50 条安全摘要，适合诊断，不适合合规审计或长期历史分析。
3. **MCP 仅覆盖本地 stdio。** 尚未支持远程 HTTP/SSE MCP 服务、多用户隔离或集中式凭据管理。
4. **Agent 执行不具备后台队列能力。** 长任务依赖当前 HTTP 流；没有断点恢复、重试、并发队列或独立任务取消 API。
5. **OCR 依赖本机额外配置。** 未准备 OCR 运行环境时，图片内容无法提取。
6. **工作区存在未跟踪测试临时目录与文件。** 它们未纳入本次提交，也不应在未确认来源前删除或加入版本控制。

## 5. 下一步建议

优先实现已确认的 **Agent 任务中心一期**：

1. 新建 `iris_agent/task_center/`，以原子 JSON 账本保存最近 100 个聊天任务与每个任务最近 100 个安全事件。
2. 在聊天与审批流旁路写入任务状态和安全时间线；不改动 `AgentLoop` 的模型与工具语义，不持久化工具参数、返回值、环境变量或原始错误。
3. 新增 `GET /api/tasks`、`GET /api/tasks/{id}` 与 `task_started` NDJSON 事件；服务重启时把未完成任务标记为中断。
4. 前端新增“任务中心”视图、任务列表与时间线，并从聊天提供“查看任务”跳转。
5. 按测试驱动方式覆盖状态流转、审批关联、敏感数据不落盘、重启恢复、API 和前端跳转，再进行全量后端与前端验证。

详细设计见 [Agent 任务中心设计](docs/superpowers/specs/2026-08-13-agent-task-center-design.md)。
