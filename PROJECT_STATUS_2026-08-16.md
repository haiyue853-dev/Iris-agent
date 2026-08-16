# 项目状态（2026-08-16）

## 1. 已完成内容

iris-agent 参照 Nous Research 的 **hermes-agent**（`D:\agent\hermes-agent`）构建的个人 AI agent，Web 形态（React + FastAPI）。当前主分支 `main`（HEAD `9b56ff0`），另有一个待合并分支 `feature/knowledge-vector-search`（HEAD `828caf7`）。

### 1.1 核心对话外壳

- 流式对话 + 工具审批 + 任务中心 + 后台任务队列（单 worker FIFO、JSON 原子账本、崩溃恢复、取消/审批）。

### 1.2 学习闭环（hermes 灵魂，P1–P4 全部落地）

| 模块 | 目录 | 能力 |
|------|------|------|
| P1 记忆系统 | `iris_agent/memory/` | `remember` 工具 + 会话自动注入 + REST API + 前端页 |
| P2 会话搜索 | `iris_agent/session_search/` | 中文 bigram 分词，`recall` 工具 + `/api/search` |
| P3 动态 Skill | `iris_agent/skill_center/` | `use_skill`/`save_skill`，正文执行 + 用户技能存储 |
| P4 子代理委派 | `iris_agent/subagent/` | `delegate_task`，工具白名单只读 + 防递归 |
| 用户画像 | `iris_agent/profile/` | LLM 自动提取 + 注入 + GET/PUT API |
| 上下文压缩 | `iris_agent/context_compression/` | 超阈值 LLM 摘要，节流每 10 轮 |

### 1.3 联网能力

| 模块 | 目录 | 能力 |
|------|------|------|
| 联网搜索 | `iris_agent/web_search/` | Bing 网页版搜索（`web_search`）+ 多源降级 + 错误自愈 |
| 网页抓取 | 同上 | `fetch_page`（httpx+bs4，SSRF 防护，反爬重试，正文容器精确定位） |
| 真浏览器兜底 | 同上 | Playwright 驱动系统 Edge（`msedge`），httpx 失败/空壳自动降级 |

### 1.4 知识库（面经收集 + 浏览 + 提问）

| 阶段 | 状态 | 内容 |
|------|------|------|
| 一期（关键词检索） | ✅ 已合并到 main | `add_knowledge`/`search_knowledge` 工具 + CRUD/search API + 前端页（列表/详情/添加/删除/提问框） |
| 二期（向量检索） | ✅ 已合并到 main（828caf7） | `OllamaEmbedder` + `EmbeddingRetriever`（余弦相似度 + 向量缓存）+ `HybridRetriever`（RRF 融合）+ 降级；已切 `retriever=hybrid` 并实测生效 |

### 1.5 周边模块

MCP 连接中心（本地 stdio）、AI 日报、UML 工作台、热点雷达 + 自动化、任务中心。

### 1.6 验证记录（最近）

- 后端 `main`（`828caf7`，含知识库二期向量检索）：**537 passed, 3 skipped, 0 failed**。
- 语义检索端到端实测（真实 Ollama `bge-m3`）：查询「多模态存储」正确召回「图文信息组织方案」，hybrid 生效。
- 前端 `web-react`：**116 passed**（24 文件），`npm run build` 通过。

## 2. 当前代码结构

```text
iris_agent/
├── bootstrap.py            # ApplicationServices / 服务装配
├── cli.py                  # 命令行入口
├── config/                 # settings.py（Settings + 各模块 Settings）
├── core/                   # AgentLoop、AgentService、models、errors
├── providers/              # ModelProvider Protocol + OpenAI 兼容实现
├── sessions/               # 会话仓储（每会话一个 JSON）
├── tools/                  # Tool 基类 + registry + builtin/（内置工具工厂）
├── memory/                 # P1 记忆（模型/仓储/服务）
├── session_search/         # P2 会话搜索（分词/模型/服务）
├── skill_center/           # P3 技能（catalog/service/bundled）
├── subagent/               # P4 子代理（模型/runner）
├── profile/                # 用户画像（模型/仓储/提取器/服务）
├── context_compression/    # 上下文压缩（compressor）
├── web_search/             # 联网搜索（search/fetcher/sources/browser_fetcher）
├── knowledge/              # 知识库（models/repository/retriever/service/embedder）
├── task_center/            # 任务中心状态机
├── task_queue/             # 后台任务队列（模型/仓储/服务）
├── mcp_center/             # MCP 连接中心
├── aihot_daily/            # AI HOT 资讯
├── hot_radar/              # 热点雷达
├── automation/             # 自动化任务
├── notifications/          # 站内通知
├── reports/                # AI 日报（仓储/服务/附件/聊天）
└── api/                    # FastAPI 路由（app.py + 各模块 *_api.py）

web-react/src/
├── App.tsx                 # 视图路由（chat/aihot/uml/reports/skills/automation/radar/mcp/tasks/memory/knowledge）
├── hooks/useChat.ts        # 后台提交、轮询、任务状态
├── api/                    # 各模块 API 客户端
└── components/             # 各视图页面 + Sidebar + ChatContainer

tests/                      # 后端 pytest（与 iris_agent/ 对应，含 memory/session_search/skill_center/subagent/profile/knowledge/web_search 等）
```

## 3. 关键参数（`agent.yaml`）

| 模块 | 参数 | 当前值 |
|------|------|--------|
| llm | model / base_url / temperature / timeout | `deepseek-chat` / `api.deepseek.com/v1` / `0.2` / `60s` |
| agent | max_tool_rounds | `8` |
| memory | max_entries / max_chars / max_injected_chars / max_injected_entries | `500` / `500` / `2000` / `20` |
| session_search | max_hit_chars / default_limit | `300` / `5` |
| skill | user_directory / max_body_chars | `data/skills/user` / `4000` |
| subagent | default_max_rounds / allowed_tools | `6` / `current_time,list_directory,read_file,recall,use_skill` |
| profile | extract_interval_rounds | `10` |
| context | trigger_chars / keep_recent / max_summary_chars | `12000` / `10` / `2000` |
| web_search | timeout / max_results / max_page_chars / max_retries | `15s` / `5` / `30000` / `2` |
| web_search | enable_browser_fallback / browser_channel | `false` / `msedge` |
| knowledge | max_content_chars / max_hit_chars / default_limit | `50000` / `500` / `5` |
| knowledge（二期） | retriever / embedding_model / embedding_base_url | `hybrid`（已启用）/ `bge-m3` / `http://localhost:11434` |

## 4. 未解决问题

### 4.1 分支待合并

- ~~`feature/knowledge-vector-search`（向量检索二期，537 passed）~~ **已合并到 main 并推送**（828caf7）。

### 4.2 旧的未合并分支（历史遗留，未继续）

- `feature/daily-report`、`feature/integrated-ai-daily-report`、`feature/interview-knowledge`、`feature/tool-approval-v02`。

### 4.3 环境问题（非代码，不影响功能）

- 本机 pytest 临时/缓存目录 ACL 损坏，跑后端测试需 `-p no:cacheprovider --basetemp=<全新目录>`。
- Windows `os.symlink(target_is_directory=True)` 静默降级（创建普通目录而非符号链接），symlink 防护测试已改为「检测未创建即 skip」。
- 已合并 worktree 物理目录残留（`browser-fallback`、`context-compression`、`knowledge-base`、`robust-fetch`、`user-profile`、`web-search` 等）及旧环境备份 `.venv314.bak`，可清理释放磁盘。

### 4.4 用户侧待办（向量检索生效前提）

- ~~需 `ollama pull bge-m3` 并以 `--embeddings` 重启 Ollama~~ **已满足**（用户已拉 bge-m3 + Ollama 已开 embeddings，`/api/embed` 实测可用），`knowledge.retriever` 已切 `hybrid`。

### 4.5 产品范围明确暂缓

- 登录、鉴权及用户隔离（用户个人自用，明确不需要）。

## 5. 下一步建议

1. ~~合并向量检索二期~~ **✅ 已完成**（828caf7 已推送）。
2. ~~让语义检索生效~~ **✅ 已完成**（bge-m3 + retriever=hybrid，实测「多模态存储」召回「图文信息组织」）。
3. **清理残留（进行中）**：已移除全部 worktree 注册（`git worktree list` 仅剩 main）+ 部分物理目录（约释放 500MB）。剩余 `.worktrees` ≈ 208MB + `.venv314.bak` 72.5MB 因 safe-delete shim「每 turn 50 次删除」上限 + 6 个 `.pytest_cache` ACL 损坏未能删完，需分多 turn 或用户确认放行 shim 后再清。
4. **可选方向**（按价值排序）：
   - curator 后台审查（记忆/技能去重、找冲突、清过期）。
   - 主动推送（日报/热点推到邮箱，从「你找它」变「它找你」）。
   - 一次性提醒/日程（现在的自动化是循环 cron，缺「3 点提醒开会」）。
   - 异步并行子代理（`delegate_task` 从同步改为并行）。
   - 多平台 gateway（单用户多端：Telegram/飞书/CLI，无需鉴权）。
