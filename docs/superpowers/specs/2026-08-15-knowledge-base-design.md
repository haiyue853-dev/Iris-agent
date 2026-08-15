# 知识库（面经收集 + 浏览 + 提问）设计规格

日期：2026-08-15
分支：feature/knowledge-base

## 1. 背景与目标

把「抓面经」的能力沉淀成**可积累、可浏览、可提问**的知识资产。用户可以把抓取的面试经验（或手动录入的内容）存入知识库，之后：

1. 在 iris 里浏览、查看、删除。
2. 在对话里提问，Agent 自动检索知识库并基于结果回答。
3. 在知识库页面里单独提问。

与已有模块的关系：
- 复用 `session_search.tokenizer.tokenize`（中文 bigram + 英文 word）。
- 存储复用 `memory.repository` 的原子写 + Windows 文件锁模式，但改为**每条目一个文件**（面经正文可达 2 万字，单文件 JSON 会膨胀）。

## 2. 数据模型

`KnowledgeEntry`（白名单字段，严格校验）：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | str | `kb-<12位hex>` | 自动生成 |
| title | str | 1–200 字 | 条目标题 |
| content | str | 1–50000 字 | 正文（完整面经/Q&A） |
| category | str | 1–50 字，默认 `面经` | 分类，用于前端筛选 |
| source_url | str \| None | 最长 2000 | 来源链接（抓取时有） |
| source_type | str | `scrape` / `manual` | 抓取 / 手动录入 |
| created_at | float | — | 创建时间戳 |
| updated_at | float | — | 更新时间戳 |

`KnowledgeSearchHit`（检索命中）：

| 字段 | 类型 | 说明 |
|------|------|------|
| entry_id | str | 命中的条目 id |
| title | str | 标题 |
| content | str | 截断后的正文片段（≤500 字） |
| source_url | str \| None | 来源 |
| score | int | 关键词重叠度 |

## 3. 存储

- 目录：`data/knowledge/`。
- **每条目一个文件**：`data/knowledge/<id>.json`，文件内容为 `KnowledgeEntry.to_dict()`。
- 写入复用 `memory.repository` 的原子写（mkstemp + fsync + os.replace）+ `msvcrt` 跨进程锁。
- `list()` 扫描目录下所有 `*.json`，读元数据（不按正文排序的完整加载，面经数量级几十条，够快）。
- 目录本身 gitignore（`data/` 已忽略），知识库是本地数据。

## 4. 检索（可插拔架构）

定义 `KnowledgeRetriever` 协议：

```python
class KnowledgeRetriever(Protocol):
    def search(self, query: str, limit: int) -> list[KnowledgeSearchHit]: ...
```

一期实现 `KeywordRetriever`：
- 复用 `tokenize(query)`，对每个条目的 `title + content` 计算 `score = len(query_tokens & doc_tokens)`。
- `score > 0` 才命中，按 `(-score, -updated_at)` 排序，取前 `limit`。
- 命中正文截断到 `max_hit_chars`（默认 500）。

**一期不做**：向量检索、混合检索、自动分块。检索器做成可插拔，以后想上 embedding 只需新增一个 retriever，不动其他代码。

## 5. 工具（Agent 侧）

| 工具 | 参数 | 说明 | 审批 |
|------|------|------|------|
| `add_knowledge` | title, content, category?, source_url? | 保存一条知识（抓取后/手动） | 否 |
| `search_knowledge` | query, limit? | 检索知识库，返回命中片段 | 否 |

- 两者均 `requires_approval=False`、只操作 `data/knowledge/`。
- `add_knowledge` 的 `source_type` 由工具内部推断（有 source_url 记为 `scrape`，否则 `manual`）。
- system prompt 补充指引：用户要求「收集/保存面经到知识库」时，用 `add_knowledge`；用户基于知识库提问时，用 `search_knowledge` 检索后回答。

## 6. REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge` | 列表（元数据，不含正文，按 updated_at 降序） |
| POST | `/api/knowledge` | 添加（title/content/category/source_url） |
| GET | `/api/knowledge/{id}` | 详情（含正文） |
| DELETE | `/api/knowledge/{id}` | 删除 |
| GET | `/api/knowledge/search?query=&limit=` | 检索（前端提问框用） |

## 7. 前端

`KnowledgePage`：
- 列表（标题 + 分类 + 来源 + 时间 + 删除按钮）
- 详情（完整正文 + 来源链接）
- 添加（标题 / 分类 / 来源 URL / 正文，手动录入）
- 独立提问框（输入问题 → 调 search API → 展示命中片段）
- 空态

侧栏加「知识库」入口。

## 8. 配置

`KnowledgeSettings`：

| 键 | 默认 | 说明 |
|------|------|------|
| directory | `data/knowledge` | 存储目录 |
| max_content_chars | 50000 | 单条正文上限 |
| max_hit_chars | 500 | 检索命中片段截断 |
| default_limit | 5 | 检索默认返回条数 |

接入 `settings.py` + `bootstrap.py` + `agent.yaml`。

## 9. 隐私与安全

- `add_knowledge` / API 只接受白名单字段，不碰工具参数、环境变量、密钥。
- 检索只对知识库正文，不碰用户会话、记忆。
- 文件写复用原子写 + 锁，避免并发损坏。
- id 由服务生成（不可由用户指定），避免路径穿越。

## 10. 一期范围

**做**：模型、仓储、关键词检索、服务、两个工具、REST API、前端页面（含提问框）、配置装配。
**不做**：向量/混合检索、自动分块、embedding、知识条目标签体系、批量导入。
