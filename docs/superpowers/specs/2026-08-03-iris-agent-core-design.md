# Iris Agent 核心框架设计

## 目标

将现有 Iris Agent 重构为一个可运行、可测试、可扩展的 Agent 核心框架。第一阶段优先完成模型调用、Agent 工具循环、会话持久化、CLI 与 FastAPI 接口，并为后续 MCP、Skills、子 Agent、长期记忆和多模态能力预留稳定边界。

第一阶段不重做 React 视觉界面，不实现 MCP、Skills、子 Agent、长期记忆、多模态，也不提供文件写入、删除或 Shell 执行工具。

## 总体方案

采用分层单体架构。核心业务不依赖 FastAPI，也不直接读取全局环境变量；CLI、HTTP API 及未来渠道共用同一个 `AgentService`。

```text
CLI / FastAPI
      |
      v
AgentService --> SessionRepository
      |
      v
 AgentLoop --> ModelProvider
      |
      v
ToolRegistry --> Built-in Tools
```

## 模块边界

```text
iris_agent/
├── core/
│   ├── agent.py          # Agent 循环与停止条件
│   ├── models.py         # Message、ToolCall、AgentEvent 等领域模型
│   └── errors.py         # 统一异常
├── config/
│   └── settings.py       # YAML、环境变量与参数合并、校验
├── providers/
│   ├── base.py           # 模型 Provider 接口
│   └── openai_compat.py  # OpenAI 兼容接口实现
├── tools/
│   ├── base.py           # Tool 定义与执行结果
│   ├── registry.py       # 注册、Schema 输出、调用分发
│   └── builtin/          # 安全内置工具
├── sessions/
│   ├── base.py           # 会话仓储接口
│   └── json_store.py     # JSON 文件仓储
├── api/
│   ├── app.py            # FastAPI 应用工厂
│   ├── schemas.py        # API 请求和响应模型
│   └── routes.py         # 对话与会话路由
└── cli.py                # 命令行入口
```

`AgentService` 协调 Provider、工具注册表和会话仓储。`AgentLoop` 只负责一次运行内的模型消息与工具调用循环。Provider 负责把领域消息转换为具体 SDK 的请求和响应。会话仓储不感知模型 SDK 或 HTTP。

根目录保留兼容入口，使 `python iris_agent.py` 和 `python server.py` 继续可用。现有 React 前端只适配新的流式事件格式。

## Agent 循环

一次对话请求执行以下流程：

1. CLI 或 API 调用 `AgentService.run(session_id, message)`。
2. 服务读取会话历史，追加用户消息并持久化。
3. `AgentLoop` 将系统提示词、历史和工具 Schema 交给 Provider。
4. 模型返回普通文本时，保存助手消息并结束。
5. 模型返回工具调用时，注册表校验工具名称和 JSON 参数，顺序执行调用并保存工具结果。
6. 将工具结果再次提交给模型，直到产生最终文本。
7. 工具轮次达到 `max_tool_rounds` 时停止，并产生可识别的循环上限错误。

首版按顺序执行同一批次中的工具调用，保证结果顺序与会话状态确定。单个工具失败会转换成结构化工具结果并交还模型，不直接破坏整个循环。Provider 调用失败则终止本次运行并输出错误事件。

## 流式事件

核心层输出统一事件，API 将事件编码为 NDJSON，CLI 根据事件类型渲染。非流式调用收集事件后返回最终响应。

事件类型如下：

- `text_delta`：模型生成的增量文本。
- `tool_started`：工具名称、调用 ID 和参数。
- `tool_finished`：工具调用 ID、结果或结构化工具错误。
- `message_completed`：本轮最终消息已持久化。
- `error`：稳定错误码和安全错误消息。

示例：

```json
{"type":"text_delta","data":{"content":"你好"}}
{"type":"tool_started","data":{"call_id":"1","name":"read_file","arguments":{"path":"README.md"}}}
{"type":"tool_finished","data":{"call_id":"1","name":"read_file","result":{"content":"..."}}}
{"type":"message_completed","data":{"message_id":"message_123"}}
```

## 配置

配置优先级固定为：

```text
构造参数 > 环境变量 > agent.yaml > 默认值
```

配置分为模型、Agent、会话与工具四组。启动时完成类型和必填项校验。API Key 仅从显式构造参数或环境变量读取，不写入日志、HTTP 响应或会话文件。

```yaml
llm:
  provider: openai_compatible
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
  temperature: 0.2
  timeout_seconds: 60

agent:
  system_prompt: 你是 Iris Agent，一个智能助手。
  max_tool_rounds: 8

sessions:
  directory: data/sessions

tools:
  enabled:
    - current_time
    - list_directory
    - read_file
  workspace_root: workspace
```

## 工具系统与安全边界

每个工具包含名称、描述、JSON Schema 和处理函数。`ToolRegistry` 负责注册冲突检查、模型 Schema 生成、参数校验和调用分发。

首版内置工具：

- `current_time`：返回指定 IANA 时区的当前时间；无参数时使用应用配置时区。
- `list_directory`：列出工作区内的直接子项，可选相对路径。
- `read_file`：读取工作区内 UTF-8 文本文件，限制最大返回字符数。

所有文件路径先相对 `workspace_root` 解析为绝对规范路径；解析 `..` 和符号链接后仍须位于工作区根目录。越界、目标类型不符、编码错误和文件过大均返回结构化工具错误。

第一阶段不注册写文件、删文件或 Shell 工具。

## 会话存储

会话仓储接口支持创建、读取、列出、追加消息、清空和删除。JSON 实现保存会话消息和元数据，列表按 `updated_at` 倒序排列。

写入采用同目录临时文件加原子替换，避免进程中断产生半截 JSON。读取到损坏文件时跳过该会话并记录警告，不主动删除用户数据。现有会话 JSON 在字段兼容时继续读取。

会话标识由服务端生成。切换和删除不存在的会话返回 `session_not_found`，不得隐式创建同名会话。

## 错误处理与日志

领域错误分为：

- `configuration_error`
- `provider_error`
- `tool_error`
- `session_error`
- `session_not_found`
- `tool_round_limit`
- `validation_error`

API 只返回稳定错误码和安全消息。异常类型、调用上下文和堆栈写入服务端日志，但日志会过滤密钥和请求头中的认证信息。工具错误可以进入 Agent 循环；Provider、会话持久化和配置错误终止当前请求。

## API 与兼容入口

保留聊天、历史和会话管理能力。流式聊天端点输出 NDJSON 事件，并以 `message_completed` 或 `error` 作为终止事件。请求中的 `session_id` 明确指定目标会话，避免依赖进程级“当前会话”导致并发串话。

根目录入口只负责加载配置、构造依赖并调用包内 CLI 或应用工厂，不保留业务逻辑。

React 前端继续使用现有页面，只修改流式解析和会话 ID 传递。第一阶段不改变布局或视觉风格。

## 测试策略

### 单元测试

- 配置优先级、默认值、类型校验和密钥隔离。
- 工作区路径越界、符号链接越界、参数校验及读取长度限制。
- 消息、工具调用和 Provider 数据转换。
- Agent 普通回复、单次与多次工具调用、工具失败恢复及轮次上限。

### 仓储测试

- 会话创建、读取、追加、清空、删除和更新时间排序。
- 原子替换、损坏 JSON 跳过及不存在会话错误。
- 可识别的旧会话格式迁移读取。

### API 测试

- 非流式聊天和 NDJSON 流式事件。
- 会话创建、切换、历史、重置和删除。
- 无效参数、未知会话、Provider 失败和稳定错误码。

Provider 测试使用假实现，不依赖真实模型或网络。OpenAI 兼容 Provider 的 SDK 边界使用 mock 验证。

## 验收标准

- 新环境安装依赖后可以启动 CLI 和 FastAPI。
- OpenAI 兼容模型能够完成普通对话与工具调用。
- 多会话可创建、读取、持久化、重启恢复、清空和删除。
- 流式接口稳定输出文本、工具状态、完成和错误事件。
- 文件工具无法逃逸配置的工作区。
- Python 测试全部通过，React 项目可以构建。
- README 和示例配置足以让新用户独立启动项目。
- 源代码及中文文档不再包含现有乱码。

## 后续扩展点

MCP 工具通过适配器注册到 `ToolRegistry`；Skills 在组装系统提示词和工具集时注入；子 Agent 可实现为受控工具或独立运行器；长期记忆通过新的仓储接口接入。这些能力不进入第一阶段实现，也不提前增加运行时复杂度。
