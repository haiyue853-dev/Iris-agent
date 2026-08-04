# Iris Agent 核心框架实施计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实施本计划。步骤使用复选框跟踪进度。

**目标：** 将现有原型重构为支持 OpenAI 兼容模型、工具循环、安全文件工具、多会话、CLI、FastAPI 和流式事件的可测试 Agent 核心框架。

**架构：** 使用分层单体，`AgentService` 组合模型 Provider、`AgentLoop`、`ToolRegistry` 和 `SessionRepository`。领域层不依赖 FastAPI 或 OpenAI SDK，外部接口通过适配器接入。

**技术栈：** Python 3.11+、OpenAI Python SDK、FastAPI、Pydantic、PyYAML、pytest、React 19、TypeScript、Vite。

---

## 文件结构

- 创建 `iris_agent/__init__.py`：公开版本和主要构造入口。
- 创建 `iris_agent/core/models.py`：消息、工具调用、模型响应和 Agent 事件。
- 创建 `iris_agent/core/errors.py`：稳定领域错误层次。
- 创建 `iris_agent/core/agent.py`：Agent 循环与 `AgentService`。
- 创建 `iris_agent/config/settings.py`：YAML、环境变量、覆盖参数和校验。
- 创建 `iris_agent/providers/base.py`：Provider 协议。
- 创建 `iris_agent/providers/openai_compat.py`：OpenAI 兼容 Provider。
- 创建 `iris_agent/tools/base.py`：工具定义、参数与执行结果。
- 创建 `iris_agent/tools/registry.py`：注册与分发。
- 创建 `iris_agent/tools/builtin/time_tool.py`：时区时间工具。
- 创建 `iris_agent/tools/builtin/files.py`：工作区目录和读取工具。
- 创建 `iris_agent/sessions/base.py`：会话实体与仓储协议。
- 创建 `iris_agent/sessions/json_store.py`：原子 JSON 仓储。
- 创建 `iris_agent/bootstrap.py`：根据配置组装生产依赖。
- 创建 `iris_agent/api/app.py`、`schemas.py`、`routes.py`：HTTP 应用。
- 创建 `iris_agent/cli.py`：CLI 渲染与交互。
- 修改 `iris_agent.py`、`server.py`：兼容入口。
- 修改 `agent.yaml`、`.gitignore`、`requirements.txt`、`README.md`：配置、依赖与文档。
- 修改 `web-react/src/types.ts`、`api/chat.ts`、`hooks/useChat.ts` 及乱码组件：新事件协议与中文修复。
- 创建 `tests/` 下对应模块测试：所有后端行为的自动化验证。

### 任务 1：建立领域模型与错误契约

**文件：**
- 创建：`iris_agent/core/__init__.py`
- 创建：`iris_agent/core/models.py`
- 创建：`iris_agent/core/errors.py`
- 测试：`tests/core/test_models.py`

- [ ] **步骤 1：编写失败测试**

```python
from iris_agent.core.models import AgentEvent, Message, ToolCall

def test_event_serializes_to_wire_shape():
    event = AgentEvent(type="text_delta", data={"content": "你"})
    assert event.to_dict() == {"type": "text_delta", "data": {"content": "你"}}

def test_message_rejects_unknown_role():
    with pytest.raises(ValueError):
        Message(role="unknown", content="x")
```

- [ ] **步骤 2：运行 `pytest tests/core/test_models.py -v`，确认因模块不存在而失败。**
- [ ] **步骤 3：实现 `Message`、`ToolCall`、`ToolResult`、`ProviderResponse`、`AgentEvent`，以及带 `code` 和安全消息的 `IrisError` 子类。**
- [ ] **步骤 4：再次运行测试并确认通过。**
- [ ] **步骤 5：提交 `feat: define agent domain models and errors`。若尚未初始化 Git，记录跳过原因。**

### 任务 2：实现类型化配置加载

**文件：**
- 创建：`iris_agent/config/__init__.py`
- 创建：`iris_agent/config/settings.py`
- 修改：`agent.yaml`
- 测试：`tests/config/test_settings.py`

- [ ] **步骤 1：编写配置优先级和校验失败测试。**

```python
def test_environment_overrides_yaml(tmp_path, monkeypatch):
    path = tmp_path / "agent.yaml"
    path.write_text("llm:\n  model: yaml-model\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    assert load_settings(path).llm.model == "env-model"

def test_explicit_override_wins_over_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "env-model")
    assert load_settings(tmp_path / "missing.yaml", model="explicit").llm.model == "explicit"
```

- [ ] **步骤 2：运行 `pytest tests/config/test_settings.py -v` 并确认失败。**
- [ ] **步骤 3：实现 `LLMSettings`、`AgentSettings`、`SessionSettings`、`ToolSettings`、`Settings` 和 `load_settings()`；API Key 只接受显式参数或环境变量。**
- [ ] **步骤 4：更新 `agent.yaml` 为已批准的分组结构并运行测试。**
- [ ] **步骤 5：提交 `feat: add validated layered configuration`。**

### 任务 3：实现工具注册表与安全内置工具

**文件：**
- 创建：`iris_agent/tools/__init__.py`
- 创建：`iris_agent/tools/base.py`
- 创建：`iris_agent/tools/registry.py`
- 创建：`iris_agent/tools/builtin/__init__.py`
- 创建：`iris_agent/tools/builtin/time_tool.py`
- 创建：`iris_agent/tools/builtin/files.py`
- 测试：`tests/tools/test_registry.py`
- 测试：`tests/tools/test_files.py`

- [ ] **步骤 1：先写注册冲突、未知工具、缺失参数、文件读取和路径越界测试。**

```python
def test_read_file_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = build_read_file_tool(workspace, max_chars=1000)
    result = tool.invoke({"path": "../secret.txt"})
    assert result.ok is False
    assert result.error_code == "path_outside_workspace"
```

- [ ] **步骤 2：运行 `pytest tests/tools -v` 并确认失败。**
- [ ] **步骤 3：实现工具定义、简单 JSON Schema 必填项/类型校验、注册表和结构化错误结果。**
- [ ] **步骤 4：实现 `current_time`、`list_directory`、`read_file`；规范化路径并验证 `Path.is_relative_to(workspace.resolve())`。**
- [ ] **步骤 5：运行工具测试并确认全部通过。**
- [ ] **步骤 6：提交 `feat: add safe extensible tool registry`。**

### 任务 4：实现 JSON 会话仓储

**文件：**
- 创建：`iris_agent/sessions/__init__.py`
- 创建：`iris_agent/sessions/base.py`
- 创建：`iris_agent/sessions/json_store.py`
- 测试：`tests/sessions/test_json_store.py`

- [ ] **步骤 1：编写增删改查、更新时间排序、不存在会话和损坏 JSON 跳过测试。**
- [ ] **步骤 2：运行 `pytest tests/sessions/test_json_store.py -v` 并确认失败。**
- [ ] **步骤 3：实现 `Session`、`SessionRepository` 协议及 `JsonSessionRepository`。写入使用同目录 `NamedTemporaryFile(delete=False)`，flush/fsync 后 `os.replace()`。**
- [ ] **步骤 4：加入现有 `session_<timestamp>.json` 与 `_meta.json` 格式的兼容读取。**
- [ ] **步骤 5：运行会话测试并确认通过。**
- [ ] **步骤 6：提交 `feat: add durable json session repository`。**

### 任务 5：实现 Provider 适配器

**文件：**
- 创建：`iris_agent/providers/__init__.py`
- 创建：`iris_agent/providers/base.py`
- 创建：`iris_agent/providers/openai_compat.py`
- 测试：`tests/providers/test_openai_compat.py`

- [ ] **步骤 1：使用 mock SDK 客户端编写普通响应、工具调用和流式文本/工具参数拼接测试。**
- [ ] **步骤 2：运行 `pytest tests/providers/test_openai_compat.py -v` 并确认失败。**
- [ ] **步骤 3：定义同步 Provider 协议，完成领域消息与 OpenAI Chat Completions 消息格式的双向转换。**
- [ ] **步骤 4：将 SDK 超时、认证和其他异常统一转换为 `ProviderError`，错误消息不得包含 API Key。**
- [ ] **步骤 5：运行 Provider 测试并确认通过。**
- [ ] **步骤 6：提交 `feat: add OpenAI-compatible model provider`。**

### 任务 6：实现 AgentLoop 与 AgentService

**文件：**
- 创建：`iris_agent/core/agent.py`
- 测试：`tests/core/test_agent_loop.py`
- 测试：`tests/core/test_agent_service.py`

- [ ] **步骤 1：创建队列式 FakeProvider，编写普通回复、单工具、多工具、工具失败、轮次上限及持久化测试。**

```python
def test_loop_executes_tool_then_returns_final_text(fake_provider, registry):
    fake_provider.queue(tool_response("call-1", "current_time", {"timezone": "UTC"}))
    fake_provider.queue(text_response("done"))
    events = list(loop.run([Message(role="user", content="time?")]))
    assert [event.type for event in events] == [
        "tool_started", "tool_finished", "text_delta", "message_completed"
    ]
```

- [ ] **步骤 2：运行两个测试文件并确认失败。**
- [ ] **步骤 3：实现循环、顺序工具执行、`max_tool_rounds` 和事件输出。**
- [ ] **步骤 4：实现服务层会话读取、用户消息预先持久化、最终消息持久化和显式 `session_id`。**
- [ ] **步骤 5：运行 `pytest tests/core -v` 并确认通过。**
- [ ] **步骤 6：提交 `feat: implement agent tool-calling loop`。**

### 任务 7：组装 CLI 与 FastAPI

**文件：**
- 创建：`iris_agent/bootstrap.py`
- 创建：`iris_agent/api/__init__.py`
- 创建：`iris_agent/api/app.py`
- 创建：`iris_agent/api/schemas.py`
- 创建：`iris_agent/api/routes.py`
- 创建：`iris_agent/cli.py`
- 修改：`iris_agent.py`
- 修改：`server.py`
- 测试：`tests/api/test_chat.py`
- 测试：`tests/api/test_sessions.py`
- 测试：`tests/test_compat_entrypoints.py`

- [ ] **步骤 1：编写应用工厂、聊天 NDJSON、错误终止事件、会话 CRUD 和兼容入口测试。**
- [ ] **步骤 2：运行 `pytest tests/api tests/test_compat_entrypoints.py -v` 并确认失败。**
- [ ] **步骤 3：实现依赖组装、Pydantic 请求模型、显式会话 ID 路由和异常映射。**
- [ ] **步骤 4：实现 CLI 事件渲染；根入口仅转发到包内实现。**
- [ ] **步骤 5：运行 API 与入口测试并确认通过。**
- [ ] **步骤 6：提交 `feat: expose agent through CLI and FastAPI`。**

### 任务 8：适配 React 客户端并修复乱码

**文件：**
- 修改：`web-react/src/types.ts`
- 修改：`web-react/src/api/chat.ts`
- 修改：`web-react/src/hooks/useChat.ts`
- 修改：`web-react/src/App.tsx`
- 修改：`web-react/src/components/ChatContainer.tsx`
- 修改：其他包含乱码的 `web-react/src/**/*.tsx`

- [ ] **步骤 1：在 `types.ts` 定义 `AgentEvent` 联合类型和单一 `Message`、`Session` 类型来源。**
- [ ] **步骤 2：让 API 方法检查 `response.ok`，聊天请求始终携带 `session_id`，并正确处理跨网络数据块的 NDJSON 残留缓冲。**
- [ ] **步骤 3：更新 `useChat`，仅将 `text_delta` 追加到回复，处理 `error` 与 `message_completed`，停止请求后保持 UI 与后端一致。**
- [ ] **步骤 4：修复 React 源码中的乱码文案，不改变布局和样式。**
- [ ] **步骤 5：运行 `npm run lint` 与 `npm run build`，预期均成功。**
- [ ] **步骤 6：提交 `fix: adapt web client to structured agent events`。**

### 任务 9：依赖、文档与全量验证

**文件：**
- 修改：`requirements.txt`
- 修改：`.gitignore`
- 修改：`README.md`
- 创建：`.env.example`
- 创建：`tests/conftest.py`

- [ ] **步骤 1：加入 `pydantic>=2`、`pytest`、`httpx` 等运行或测试依赖，并忽略 `.env`、会话数据、构建产物和缓存。**
- [ ] **步骤 2：重写 README，包含 Python 版本、安装、环境变量、CLI/API/前端启动、配置项、工具安全边界和测试命令。**
- [ ] **步骤 3：创建不含真实密钥的 `.env.example`，确认现有 `.env` 被忽略且不输出内容。**
- [ ] **步骤 4：运行 `python -m pytest -q`，预期全部通过。**
- [ ] **步骤 5：运行 `python -m compileall iris_agent iris_agent.py server.py`，预期无语法错误。**
- [ ] **步骤 6：在 `web-react` 运行 `npm run lint` 和 `npm run build`，预期成功生成 `dist/`。**
- [ ] **步骤 7：运行 `rg -n "锛|鍙|浼|绔|TODO|待定" --glob '!node_modules/**' --glob '!data/**' --glob '!docs/superpowers/**'`，逐项确认没有乱码或占位内容。**
- [ ] **步骤 8：使用 FakeProvider 或 mock 客户端完成一次 API 冒烟验证：创建会话、发送消息、读取完成事件、重启仓储并恢复历史。**
- [ ] **步骤 9：提交 `docs: document Iris Agent core framework`。**

## 最终自检

- 每一项设计需求均映射到任务 1 至 9。
- 所有外部网络行为均由 Provider 边界隔离，自动化测试不访问真实模型。
- API 不依赖全局当前会话，避免并发请求串话。
- 文件工具不包含写入、删除或 Shell 能力。
- 旧入口与可识别的旧会话格式均有兼容测试。
- 只有在完整验证命令产生成功输出后，才能宣称实现完成。
