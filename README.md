# Iris Agent

Iris Agent 是一个参考 Hermes Agent 架构思想开发的轻量 Agent 框架。当前版本提供 OpenAI 兼容模型、工具调用循环、安全文件工具、多会话持久化、CLI、FastAPI 和 React 对话界面。

## 环境要求

- Python 3.11 或更高版本
- Node.js 20 或更高版本（仅开发 Web 前端时需要）

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，填入模型服务密钥。默认配置使用 DeepSeek 的 OpenAI 兼容接口，也可以通过 `OPENAI_BASE_URL` 和 `LLM_MODEL` 接入其他兼容服务。

配置优先级为：构造参数、环境变量、`agent.yaml`、默认值。密钥只从环境变量或显式构造参数读取。

## 启动

CLI：

```powershell
python iris_agent.py
```

API：

```powershell
python server.py
```

API 文档位于 <http://localhost:8000/docs>，健康检查位于 <http://localhost:8000/api/health>。

React 前端：

```powershell
Set-Location web-react
npm install
npm run dev
```

然后访问 <http://localhost:5173>。

## 核心结构

```text
iris_agent/
├── core/       # Agent 循环、领域模型和错误
├── config/     # 配置加载与校验
├── providers/  # 模型 Provider 适配器
├── tools/      # 工具注册表与内置工具
├── sessions/   # 会话仓储
├── api/        # FastAPI 应用
├── bootstrap.py
└── cli.py
```

一次调用的数据流为：`CLI/API → AgentService → AgentLoop → Provider/ToolRegistry → SessionRepository`。

## 内置工具和安全边界

- `current_time`：获取指定 IANA 时区的时间。
- `list_directory`：列出 `workspace/` 内的目录。
- `read_file`：读取 `workspace/` 内的 UTF-8 文本并限制返回长度。

文件路径规范化后必须仍位于 `workspace_root` 内。当前版本不提供写文件、删除或 Shell 执行工具。

## 流式协议

`POST /api/chat/stream` 返回 NDJSON，事件包括 `text_delta`、`tool_started`、`tool_finished`、`message_completed` 和 `error`。请求必须显式携带 `session_id`，避免并发会话串话。

## 测试

```powershell
python -m pytest -q
Set-Location web-react
npm run lint
npm run build
```

详细设计与实施计划位于 `docs/superpowers/`。
