# 记忆系统一期设计（P1）

日期：2026-08-15  
状态：方案待确认

## 目标与范围

让 Iris 跨会话记住用户的关键事实、偏好与项目背景，并在每次对话开始时把相关记忆注入系统提示，使 Agent 越用越懂用户。

一期只做「记忆存储 + 会话注入 + 记忆 CRUD + 主动记忆工具」，不引入全文搜索（P2）、自动技能（P3）或用户画像建模。记忆的一期写入来源为：用户/前端手动添加，以及 Agent 通过内置 `remember` 工具主动保存——这是 hermes「自动学习」的轻量形态，Agent 自己判断何时该记，无需对话结束后的额外 LLM 提取调用。

## 方案选择

- **JSON 原子仓储**：复用 `task_queue/repository.py` 的临时文件替换 + `fsync` + Windows 一字节文件锁模式，与 `data/task_queue` 同构。一期记忆量小，无需 SQLite/FTS5。
- **注入方式**：把相关记忆作为额外 `system` 消息注入，放在 `system_prompt` 之后、会话消息之前，不改动 `AgentLoop` 的模型与工具语义。
- **主动记忆工具**：新增只读安全度的 `remember` 内置工具，`requires_approval=False`；它只保存 Agent 显式提交的 `content` 与 `category`，不触碰工具参数、工具结果、环境变量或密钥。

## 数据模型

`MemoryEntry`（`iris_agent/memory/models.py`）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | `str` | `memory_<hex>` |
| `content` | `str` | 1–500 字符，非空白 |
| `category` | `str` | 白名单 `preference` / `fact` / `project` / `other` |
| `created_at` | `str` | ISO 8601 |
| `updated_at` | `str` | ISO 8601 |
| `source_session_id` | `str \| None` | 来源会话，可为空 |

严格校验白名单字段；拒绝未知 category、超长或空白 content，不落盘任何额外 payload。

## 存储

`data/memory/memory.json`，结构 `{"entries": [...]}`。`MemoryRepository` 提供 `load()` / `save()`，复用原子写与 Windows 文件锁。上限由 `MemorySettings.max_entries` 约束（默认 500），超出时按 `updated_at` 淘汰最旧条目。

## 服务与注入

`MemoryService`：

- `add(content, category, source_session_id=None) -> MemoryEntry`
- `list() -> list[MemoryEntry]`（按 `updated_at` 倒序）
- `delete(entry_id) -> None`
- `inject() -> list[MemoryEntry]`：按 `updated_at` 倒序取最近条目，累计字符数不超过 `max_injected_chars`（默认 2000）、条数不超过 `max_injected_entries`（默认 20）。

注入发生在 `AgentService.run()` 与 `resolve_tool_approval()` 组装 messages 时：

```python
messages = [Message(role="system", content=self.system_prompt)]
for memory in self.memory.inject():
    messages.append(Message(role="system", content=f"[记忆·{memory.category}] {memory.content}"))
messages.extend(session.messages)
```

注入内容在会话开始时确定、中途不变化，保护未来启用 prompt 缓存的空间。记忆为空时注入零条，行为与现状一致。

## 主动记忆工具

`iris_agent/tools/builtin/memory_tool.py`：

```python
def build_remember_tool(memory: MemoryService) -> Tool:
    def remember(content: str, category: str = "fact"):
        entry = memory.add(content, category)
        return {"id": entry.id, "content": entry.content, "category": entry.category}
    return Tool("remember", "记住一条关于用户的长期信息，供后续对话使用", {...}, remember, requires_approval=False)
```

工具参数 `content`（必填）、`category`（可选，默认 `fact`）。工具执行错误（非法 category、超长等）通过 `ToolInvocationError` 返回安全错误码。

## HTTP API

新增 `iris_agent/api/memory_api.py`：

| 接口 | 作用 |
| --- | --- |
| `GET /api/memory` | 返回记忆列表（白名单字段，倒序） |
| `POST /api/memory` | 添加记忆，返回新建条目 |
| `DELETE /api/memory/{id}` | 删除记忆，不存在返回 404 |

请求模型仅含 `content`、`category`；响应不含任何敏感 payload。

## 配置与装配

`MemorySettings`（`config/settings.py`）：

| 参数 | 默认 |
| --- | --- |
| `directory` | `data/memory` |
| `max_entries` | `500` |
| `max_chars` | `500` |
| `max_injected_chars` | `2000` |
| `max_injected_entries` | `20` |

`bootstrap.py` 构造 `MemoryService`，把 `build_remember_tool(memory)` 注册进 `ToolRegistry`，并把 `memory` 传给 `AgentService`。`agent.yaml` 新增 `memory:` 配置节（默认值可用）。

## 前端

新增「记忆」页面：列出记忆（内容 + 类别 + 时间）、添加表单、删除按钮；接入侧栏导航与 `GET/POST/DELETE /api/memory`。聊天侧无需 UI 改动——`remember` 工具由 Agent 自动调用，其过程通过现有工具事件与审批卡片机制展示（只读工具不触发审批）。

## 错误处理与约束

- 账本损坏或不可写时，读取接口返回安全错误，不泄露账本路径或原始异常。
- 非法 `category` / 空 content / 超长 content 返回 422 或领域错误码。
- 记忆只影响目标会话的注入，不影响其他会话、任务中心或历史数据。
- 记忆是用户显式要 Agent 记住的信息；系统绝不自动扫描会话、不自动抽取工具参数/结果/密钥/环境变量存入记忆。

## 测试与验收

后端覆盖：

- 记忆 add/list/delete 生命周期、白名单字段校验与脱敏；
- `inject()` 的条数与总字符数上限、按 `updated_at` 排序、空账本返回空；
- `remember` 工具保存成功与非法参数错误码；
- `AgentService` 注入：有记忆时 messages 含对应 system 条目，无记忆时不注入；
- `MemoryService` 装配与 REST API 的校验、404、字段白名单。

前端覆盖：

- 记忆列表渲染、添加、删除与空态；
- 导航接入。

验收标准：手动或 Agent 主动保存的记忆能在新会话开始时注入系统提示；非法与敏感数据不落盘、不出现在任何接口；记忆为空时对话行为与现状完全一致。
