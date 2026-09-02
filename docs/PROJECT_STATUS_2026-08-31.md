# Iris Agent 项目状态（2026-08-31）

## 1. 已完成内容

### RAG 知识库

- 已从基础本地知识库扩展为 RAG 工作流：文档导入、文本抽取、父子分块、向量索引、混合检索、重排、上下文组装与回答引用。
- 已支持 PDF、DOCX、XLS/XLSX、PPTX、HTML/MHTML、Markdown、TXT 与常见图片格式导入；资料存入 SQLite，原始文件单独保存。
- 已支持知识库集合、主题筛选、资料批量移动/删除/重建索引、检索策略、导入进度和失败重试。
- 已接入本地 Ollama 向量模型（默认 `bge-m3`）、本地知识图谱抽取、可选云端语义拆分和可选重排器。
- 已实现文档思维导图、跨资料关系图、实体/关系编辑、图谱质量检查与同义实体合并入口。
- 已完成“云端语义拆分、本地问答”的运行时配置界面；拆分密钥只从环境变量读取，不会展示在前端。

### 聊天与引用

- 聊天回答可附带知识库引用；回答内的 `[数字]` 可展开对应的命中来源，再打开资料并定位到原始切片。
- 已修复引用标记被浏览器当作自定义协议跳转、导致切换到空白新聊天的问题；现在使用页内安全标记。
- 已提供 RAG 流水线进度、知识库引用卡片、来源评分、提示词优化、Skill 选择与工具结果展示。

### 知识库页面体验

- 已按 WeKnora 风格重构知识库的三栏工作区，并保留 Iris 原有的灰白主题。
- 搜索/导入区不再随内容滚动固定；页面采用主页面滚动，减少被小容器截断的情况。
- 右侧“资料详情”关闭后会保留当前资料，并在主区域提供“打开资料详情”入口；重新点击资料、检索结果或图谱来源也会打开详情。

### 会话与基础能力

- 已迁移到组合式左侧栏，包含聊天、日报、资讯、流程图、Skills、自动化、知识库、任务、记忆、MCP 与消息渠道入口。
- 已修复会话生成锁导致“列表里存在但无法打开或删除”的问题：会话读取和删除不再等待长时间模型调用锁。
- 用户已于 2026-08-31 清空全部聊天会话；知识库和长期记忆未删除。

## 2. 当前代码结构

```text
Iris-agent/
├─ server.py                         # FastAPI 服务启动入口
├─ start.ps1 / start.cmd             # 后端与 Vite 前端启动脚本
├─ agent.yaml                        # 非敏感运行配置
├─ .env                              # 本机密钥与环境变量（不应提交）
├─ data/
│  ├─ sessions/                      # 聊天会话 JSON 文件
│  ├─ knowledge/                     # 知识库 SQLite 与原始资料
│  └─ ...                            # 任务、记忆、技能等运行数据
├─ iris_agent/
│  ├─ api/                           # HTTP 接口：聊天、知识库、Skills、MCP、渠道等
│  ├─ bootstrap.py                   # 服务装配与依赖初始化
│  ├─ config/                        # 配置加载、校验与默认值
│  ├─ core/                          # Agent 循环、模型、运行时快照
│  ├─ knowledge/                     # RAG 主实现
│  │  ├─ parsing/                    # 多格式解析器
│  │  ├─ chunker.py                  # 父子分块
│  │  ├─ semantic_splitter.py        # 云端语义拆分
│  │  ├─ embedder.py                 # 向量化
│  │  ├─ reranker.py / reranking/    # 重排
│  │  ├─ sqlite_repository.py        # 知识库持久化
│  │  ├─ rag_service.py              # 导入、索引、检索与运行时配置
│  │  ├─ mindmap.py                  # 文档思维导图
│  │  └─ orchestrator.py             # 后台导入/索引编排
│  ├─ sessions/                      # JSON 会话存储
│  ├─ skill_center/                  # 内置与用户 Skill
│  ├─ task_center/ task_queue/       # 后台任务与队列
│  ├─ tools/                         # Agent 工具注册与内置工具
│  └─ gateway/                       # QQ、NapCat、企业微信等渠道
├─ web-react/
│  ├─ src/App.tsx                    # 视图切换与聊天/知识库联动
│  ├─ src/components/app-sidebar.tsx # 左侧导航与会话列表
│  ├─ src/components/AssistantChat.tsx
│  ├─ src/components/assistant-ui/   # 聊天消息、Markdown、引用、Skill 菜单
│  ├─ src/components/knowledge/      # 知识库页面、图谱、思维导图、RAG 配置
│  ├─ src/api/                       # 前端 API 客户端
│  └─ src/App.css                    # 全局主题与页面布局
└─ tests/                            # Python 后端测试
```

## 3. 关键参数

以下是 `agent.yaml` 中当前默认值；知识库页面的“RAG 运行状态”可覆盖部分模型开关、模型名、地址与 MMR 权重。

| 类别 | 参数 | 当前值 | 说明 |
| --- | --- | --- | --- |
| 分块 | `chunk_strategy` | `parent_child` | 父子分块策略 |
| 分块 | `parent_chunk_target_chars` | `1800` | 父块目标字符数 |
| 分块 | `child_chunk_target_chars` | `450` | 检索命中的子块目标字符数 |
| 分块 | `child_chunk_overlap_chars` | `80` | 子块重叠字符数 |
| 检索 | `retriever` | `hybrid` | 关键词与向量混合检索 |
| 检索 | `retrieval_limit` | `5` | 默认返回候选数 |
| 检索 | `minimum_relevance_score` | `0.2` | 最低相关性阈值 |
| 检索 | `max_context_chars` | `6000` | 提交给回答模型的知识上下文上限 |
| 向量 | `embedding_model` | `bge-m3` | Ollama 本地向量模型 |
| 向量 | `embedding_base_url` | `http://localhost:11434` | Ollama 服务地址 |
| 语义拆分 | `semantic_split_enabled` | `false` | 默认未启用，启用后仅用于新导入资料 |
| 语义拆分 | `semantic_split_model` | `qwen-plus` | 可改为 DeepSeek 的 `deepseek-chat` |
| 语义拆分 | `semantic_split_timeout_seconds` | `180` | 云端拆分超时秒数 |
| 图谱 | `graph_extraction_enabled` | `true` | 导入时抽取知识图谱 |
| 图谱 | `graph_extraction_model` | `deepseek-r1:8b` | 本地 Ollama 图谱模型 |
| 重排 | `reranker_enabled` | `true` | 默认启用 |
| 重排 | `reranker_provider` | `ollama` | 可选 `ollama`、`api`、`none` |
| 重排 | `reranker_candidates` | `15` | 重排的候选切片数 |
| 融合 | `rrf_k` | `60` | RRF 融合参数 |
| 融合 | `retrieval_candidate_multiplier` | `3` | 初召回候选倍率 |

### 密钥与模型地址

- 云端语义拆分读取 `RAG_SPLIT_API_KEY`；未设置时回退读取 `OPENAI_API_KEY`。
- 使用 DeepSeek 云端拆分时，建议：服务地址 `https://api.deepseek.com/v1`，模型 `deepseek-chat`。密钥仅写入 `.env`，不要写入 `agent.yaml`、文档或前端。
- 本机此前安装过 `deepseek-r1:8b`、`bge-m3:latest` 与 `qwen3.5:4b`；本次文档生成时未重新调用 Ollama 进行可用性校验。

## 4. 未解决问题与风险

### RAG 质量

- 当前最主要问题是资料内容质量与分块边界：抓取网页中的“已生成草稿”“来源链接”“过程提示”等文本可能被入库，并在问答时被召回。
- 面试问答资料若没有稳定标题和问答边界，可能出现只命中问题、只命中答案或命中网页摘要。当前 450 字子块对“问题 + 长答案”并不总能完整覆盖。
- 已删除资料的旧引用会保留在旧会话历史中；聊天会话已清空后该影响暂时消失，但将来仍应在 UI 中标注“历史来源已不存在”。
- 云端语义拆分默认关闭；启用或修改拆分模型后，已有资料需要重新索引才能应用新的拆分结果。

### 运行与工程状态

- 本次生成文档时，`http://127.0.0.1:8000/api/knowledge/runtime` 无法连接，说明后端服务当时未在该端口运行或刚被停止；因此无法确认当前实际生效的运行时模型配置。
- 工作区存在大量已修改和未追踪文件，尚未提交；其中包含功能代码、测试、文档和大量 `.tmp-pytest-*` 临时目录。当前不应在未确认归属前批量清理或回滚。
- 已执行的近期验证以定向测试为主：知识库页面测试、Markdown 引用测试、会话存储测试均曾通过；尚未在 2026-08-31 对整个 Python/前端测试集做全量回归。
- Vite 打包会提示主 JavaScript 产物超过 500 kB；当前不影响运行，但后续可按需做懒加载拆包。

## 5. 下一步建议

1. 启动后端和前端后，先在“知识库 → 管理与评测 → RAG 运行状态”检查 Ollama、向量、图谱、重排连接状态，再导入新资料。
2. 为面试知识采用固定资料模板：`问题`、`答案`、`要点/追问`；每题使用二级标题或 `---` 分隔，避免将导入过程文本、URL 列表和草稿提示写入正文。
3. 选取 5～10 份代表性资料做一次分块抽样：检查标题是否和正文在同一父块、问题和答案是否同一检索单元；再决定调整 `child_chunk_target_chars`（例如 600～800）还是启用云端语义拆分。
4. 对已混入无效摘要的资料进行删除或编辑后重新索引；不要仅修改配置而不重建旧资料的索引。
5. 新建一组固定问答作为检索回归用例，记录“问题 → 应命中文档/切片”，用来观察配置调整是否真的提高召回。
6. 功能稳定后，将当前改动按功能分批提交；临时测试目录和历史测试产物需先由使用者确认，再单独清理。

## 最近验证记录

| 日期 | 项目 | 结果 |
| --- | --- | --- |
| 2026-08-30 | `web-react` 知识库页面定向测试 | 21 项通过 |
| 2026-08-30 | `web-react` Markdown 引用定向测试 | 3 项通过 |
| 2026-08-30 | `web-react` 生产构建 | TypeScript 与 Vite 构建通过 |
| 2026-08-31 | 会话存储定向测试 | 9 项通过 |

> 本文记录的是当前工作区状态，不包含任何 API 密钥或 `.env` 内容。
