# Iris Agent

Iris Agent 是一个参考 Hermes Agent 架构思想开发的轻量个人效率 Agent。当前版本提供 OpenAI 兼容模型、工具调用循环、安全文件工具、多会话持久化、CLI、FastAPI、React 对话界面和独立的日报助手。

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

Windows 下可以在项目根目录双击 `start.cmd`，或在 PowerShell 中运行：

```powershell
.\start.ps1
```

脚本会分别启动后端和 React 前端。浏览器访问 <http://localhost:5173>，左侧可以在“聊天”和“日报”之间切换。

也可以分别启动各部分：

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

## 日报助手

日报页面用于把零散工作记录整理为固定的汇报版日报，包含“今日完成、进行中、遇到的问题、明日计划、需要协助”五个章节。

1. 在“工作记录”中写下当天完成事项、问题和计划。
2. 如果希望引用聊天里的工作内容，先在聊天页选中会话，再勾选“导入当前对话”。
3. 点击“生成汇报版日报”。生成过程只调用模型，不会执行 Agent 工具。
4. 可以直接编辑五个章节，页面会在停止输入约 600 毫秒后自动保存。
5. 在“AI 修改要求”中输入“更简短，突出成果”等要求，可生成一个新版本。
6. 左侧历史区可以按日期打开日报，也可以把旧版本恢复为一个新版本。
7. 完成后可以复制 Markdown，或下载 `.md` 文件。

日报按日期保存在本机 `data/reports/`，默认每份最多保留 20 个版本。手动记录最多 50,000 字，AI 修改要求最多 2,000 字；这些限制可以在 `agent.yaml` 的 `reports` 中调整。当前日报功能不会自动联网、搜索热点、定时运行或执行工具，聊天内容也只有在主动勾选时才会作为本次生成的快照保存。

## 核心结构

```text
iris_agent/
├── core/       # Agent 循环、领域模型和错误
├── config/     # 配置加载与校验
├── providers/  # 模型 Provider 适配器
├── tools/      # 工具注册表与内置工具
├── sessions/   # 会话仓储
├── reports/    # 日报生成、版本和本地存储
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
npm test
npm run lint
npm run build
```

详细设计与实施计划位于 `docs/superpowers/`。
