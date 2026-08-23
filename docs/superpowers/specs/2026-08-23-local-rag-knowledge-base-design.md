# 本地 RAG 知识库设计规格

日期：2026-08-23

## 目标

将现有“单条知识 + 关键词/向量检索”升级为单机本地 RAG。用户可上传 PDF、DOCX、XLSX、Markdown 与 TXT；系统提取文本、持久化分块与向量，并在聊天时自动检索、注入相关片段、展示可追溯引用。

所有原文、索引和向量只保存在 Iris 数据目录；嵌入仅调用本机 Ollama 的 `bge-m3`。

## 非目标

- 不接入云端 embedding、外部向量数据库或后台服务。
- 不做 OCR；扫描 PDF 或纯图片文档标为无法提取。
- 不做网页同步、定时抓取或多人权限。
- 不修改现有手动知识和网页抓取的公开 API；它们会被迁移到统一文档模型。

## 架构

新增 `knowledge_documents` 子模块，现有 `knowledge` 作为兼容门面。数据目录改为一个 SQLite 数据库和受控原文件目录：

```
data/knowledge/
  knowledge.db          # documents、chunks、FTS5、embeddings、migration 元数据
  files/<uuid>.<suffix> # 用户上传的原始资料
```

SQLite 使用事务写入、外键和 FTS5。借鉴 Hermes 的本地 SQLite/FTS5 原则，但不复制 Hermes 的会话表或运行时依赖。对于单进程本地 Iris，优先 WAL；若系统 SQLite 或目录不支持 WAL，则安全退回 DELETE journal 模式并记录告警。

### 数据模型

`documents`：资料元数据：ID、显示名、来源类型（upload/manual/scrape）、MIME、大小、原文件名、创建时间、索引状态（queued/indexing/ready/failed）、错误摘要。

`chunks`：ID、document ID、顺序、正文、定位信息（页码/段落/工作表/行范围）、正文哈希。

`chunk_embeddings`：chunk ID、embedding 模型标识、维度、向量 JSON/blob、正文哈希、创建时间。正文或模型变化时只重建受影响切片。

`chunks_fts`：FTS5 索引 `title + content`，用于中文关键词召回。需要 CJK 扩展时按可选能力加载；扩展不可用时使用标准 FTS5 和现有 bigram tokenizer 兜底。

## 资料生命周期

1. 上传时在 I/O 前检查类型、大小、总量、数量和文件名；服务端以 UUID 保存原文件，绝不把用户文件名当作路径。
2. 使用既有安全提取器抽取文本；记录可定位的来源片段。空文本或不支持的格式进入 `failed`，不写入可检索内容。
3. 文本按约 800 中文字符、120 字符重叠切片；优先在句子、段落、页和工作表边界断开。每个切片保留原始定位。
4. 分批调用本机 Ollama `/api/embed`，默认模型 `bge-m3`。写入 embeddings 后在一个事务内标记资料 `ready`。
5. 删除资料时在同一事务中删除 FTS、切片和向量，再删除受控原文件；文件删除失败会保留待清理标记而不暴露路径。

索引在请求线程外的受控本地 worker 完成。API 可查询状态；重启时恢复 `queued/indexing` 的未完成资料。Ollama 不可用时保留 `queued/failed` 明确信息，关键词检索仍可用于已有文本。

## 检索与聊天注入

每条用户消息在调用聊天模型前执行：

1. 对最新用户问题执行 FTS5 检索与本地向量检索。
2. 以 RRF 融合结果，保留最多 6 个切片、最多 6,000 字符上下文。
3. 仅当最佳混合得分达到配置阈值时注入；否则正常对话，不制造“知识库来源”。
4. 注入内容以稳定、独立的 `知识库参考资料` 消息放入本轮模型请求，不回写既有会话历史；避免改变历史消息和污染后续存档。
5. 模型提示要求仅在使用资料时按 `[来源 n]` 标记。服务端把这些标记映射为 document ID、标题和定位，随 `message_completed` 事件返回。

聊天页面把引用渲染在回答末尾，展示资料标题与页码/段落/工作表，可点击打开知识库中对应资料和片段。模型没有引用标记时不展示来源，即使检索曾命中。

## API 与前端

新增资料 API：

- `GET /api/knowledge/documents`：资料列表和索引状态。
- `POST /api/knowledge/documents`：multipart 上传。
- `GET /api/knowledge/documents/{id}`：资料、片段与定位。
- `DELETE /api/knowledge/documents/{id}`：级联删除。
- `GET /api/knowledge/search`：返回切片级命中与引用定位，兼容旧查询参数。

知识库页面改为：上传区、资料列表、索引状态、检索预览与资料详情。保留手动录入入口，录入内容作为 `manual` 文档进入同一分块/索引流程。原有网页抓取知识作为 `scrape` 文档迁移。

## 配置与故障处理

扩展 `knowledge` 配置：数据库路径、文件目录、允许格式、单文件/总量/数量限制、chunk 大小/重叠、向量批大小、召回数量、上下文字符上限和相关度阈值。`embedding_model`、`embedding_base_url` 与超时沿用现有 Ollama 配置。

所有 API 响应不返回服务器原始路径或完整向量。上传、提取、索引与检索失败返回稳定错误码；Ollama 离线只影响语义召回，不影响 FTS5/关键词检索或普通聊天。

## 迁移与兼容

首次启动时读取现有每条 JSON 知识记录并导入 SQLite，记录迁移版本后不重复导入。迁移失败保留源 JSON、不删除数据，并报告可重试状态。现有 `add_knowledge` 与 `search_knowledge` 工具保持名称和参数不变，内部改为调用新服务。

## 测试与验收

- 单元测试：文件安全、提取、切片边界、FTS、向量批处理、RRF、阈值、删除级联与迁移幂等。
- API 测试：上传、状态、搜索、引用定位、失败状态和路径脱敏。
- 聊天集成测试：相关问题注入并返回引用；无关问题不注入；Ollama 失败时关键词降级；原历史消息不变。
- 前端测试：上传状态、资料删除、检索命中、回答引用跳转。
- 手工验收：上传一份多页 PDF 与一份 Excel，问题命中对应页/工作表，重启后不重新向量化已就绪切片。
