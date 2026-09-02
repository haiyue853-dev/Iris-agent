# Iris Agent 对标 WeKnora 升级计划：RAG 管线 + 对话页面

- 文档版本：v1
- 编制日期：2026-08-30
- 对标对象：`D:/agent/WeKnora-main/WeKnora-main`（WeKnora v0.7.2，Go 版）
- 改造对象：Iris Agent（`iris_agent/knowledge/`、`iris_agent/attachments/`、`web-react/src/`）
- 参考文档：`docs/PROJECT_STATUS_2026-08-26.md`、`docs/competitive-analysis-2026-08-23.md`

---

## 0. 目标与范围

### 0.1 两个目标

1. **RAG 管线达到 WeKnora 的工程形态**：独立的文档解析层、策略化切片、可插拔的向量/检索/重排组件、引用可追溯、检索效果可评测。核心思想是"每一层都是策略模式 + 注册表"，而不是现在把能力写死在一个 `rag_service.py`（692 行）里。
2. **对话页面仿照 WeKnora**：引用气泡 + 引用抽屉、RAG 管线分阶段进度、流式 Markdown 渲染、工具调用过程展示、回答后追问建议、会话按来源分组。

### 0.2 非目标（明确不做）

- 不做多租户 / RBAC / 审计日志——Iris 定位是单用户个人 Agent，这是与 WeKnora 的定位差异，不是缺陷。
- 不引入独立 docreader 微服务（Go + gRPC）——单进程部署是 Iris 的优点，用**进程内 parser 包**达到同等可扩展性即可。
- 不迁移向量库到 Milvus/ES——个人数据量级下 SQLite 足够，但要补上**向量索引**（见 Phase 3）。
- 不砍掉 Iris 已有的差异化能力（子 Agent 委派、思维导图、QQ 渠道）。

### 0.3 总体原则

- 每个阶段结束都必须保持 `python -m pytest -q` 全绿 + `web-react` lint/build 通过，才允许进入下一阶段。
- 优先"换内脏不换皮肤"：后端接口尽量保持兼容，前端跟随 WeKnora 的交互重画。
- WeKnora 是 MIT 协议，可以**读它的实现思路并参考 prompt 模板**（`config/prompt_templates/`），但 Iris 是 Python，代码要自己写。

---

## 1. 差距清单（现状 → 目标）

| # | 环节 | Iris 现状 | WeKnora 参照 | 差距等级 |
|---|------|-----------|--------------|----------|
| 1 | 文档解析 | `attachments/extraction.py` 按扩展名抽文本，格式少、无图片 OCR、无公式/表格处理 | `docreader/parser/`：24 个 parser 文件，按类型注册（pdf/docx/excel/pptx/epub/mhtml/image/xmind/web），支持 chain_parser 组合 | ★★★ |
| 2 | 切片 | `knowledge/chunker.py` 100 行，固定 800/120 字符滑窗 | 自适应三级切片 + 父子切片（parent-child chunking），`docreader/splitter/splitter.py` | ★★★ |
| 3 | 向量存储 | `sqlite_repository.py` 存 embedding JSON，检索时 Python 全表遍历算相似度 | pgvector + HNSW 索引，多引擎可插拔 | ★★☆ |
| 4 | 检索 | `retriever.py` 关键词 CJK-bigram + 向量混合，固定 hybrid | BM25（真·倒排索引）+ 稠密 + 图谱多路召回，可配权重/阈值 | ★★☆ |
| 5 | 重排 | `reranker.py` 用 Ollama chat 模型 prompt 打分（不稳定、慢） | 独立 rerank provider（bge-reranker / 腾讯 LKEAP / 火山引擎，批式请求） | ★★★ |
| 6 | 引用与溯源 | 有引用展示，但 chunk 与文档的溯源链路简单 | inline 引用 popover + 来源抽屉（区分知识库/网页）+ chunk 级版本历史 | ★★☆ |
| 7 | 评测 | 无 | 召回命中率 + BLEU/ROUGE 端到端评测管线 | ★★☆ |
| 8 | 对话页面 | assistant-ui 已有流式、工具卡片、引用，但形态偏"调试台" | 气泡式对话 + 引用 popover + 管线进度条 + 追问建议 + Markdown 导出 | ★★★ |
| 9 | 知识库管理页 | 集合/文档列表 + 图谱可视化 | 文件夹树 + 批量操作 + chunk 在线编辑（带修订历史）+ 召回测试 | ★★☆ |

---

## 2. Phase 1 —— 文档解析层（对应差距 #1）

**目标**：把"上传附件抽文本"升级为"WeKnora 式 parser 注册表"，任何新格式只需新增一个 parser 文件。

### 2.1 新建 `iris_agent/knowledge/parsing/` 包

```
iris_agent/knowledge/parsing/
├── base.py          # DocumentParser 协议: parse(source, config) -> ParsedDocument
├── models.py        # ParsedDocument / ParsedSection(含 section_type: text|table|image|formula)
├── registry.py      # 按扩展名 + MIME 注册，替代散落的 if-elif
├── pdf_parser.py    # pymupdf：文本层优先，无文本层走 OCR
├── office_parser.py # docx/python-docx, xlsx/openpyxl, pptx/python-pptx
├── html_parser.py   # trafilatura 或 BeautifulSoup（含 mhtml）
├── markdown_parser.py
├── image_parser.py  # 接入 VLM 描述（先 Ollama llava/qwen-vl，降级跳过）
└── chain.py         # 组合式解析（如 docx -> 图片子元素再交给 image_parser）
```

参照 `docreader/parser/base_parser.py`（`Parser` 抽象 + `ParserRegistry`）和 `chain_parser.py` 的组合思路。

### 2.2 与现有模块的接驳

- `attachments/service.py` 抽取文本的逻辑改为调用该 registry；附件走聊天场景与知识库导入场景共用同一套 parser。
- 解析结果持久化到 `data/knowledge/` 下（原文件 + 解析产物 JSON），为 Phase 2 的"重新解析"提供基础。
- 每次解析记录**阶段耗时**（下载/抽取/OCR/切分），为 Phase 5 的"管线进度"提供数据来源。

### 2.3 验收标准

- 支持格式：PDF、DOCX、XLSX、PPTX、MD、HTML/MHTML、TXT、图片（VLM 描述）。
- 上传一个含表格和图片的 PDF，解析产物中能区分 text/table/image 三类 section。
- 新增 parser 注册表单测；解析失败有明确错误类型而非静默空文本。

---

## 3. Phase 2 —— 切片升级：父子切片 + 自适应（对应差距 #2）

**目标**：检索命中子块、返回给 LLM 的是父块上下文——这是 WeKnora v0.3.3 引入、对长文档召回质量提升最大的一项。

### 3.1 改造 `knowledge/chunker.py`

- 保留现有固定切片作为 fallback。
- 新增 `ParentChildChunker`：
  - 父块：按 Markdown 标题/段落结构切，目标 1500–2000 字符（参照 WeKnora 的 header_hook 思路，`docreader/splitter/header_hook.py`）。
  - 子块：父块内 300–500 字符滑窗（重叠 80）。
  - SQLite 表 `chunks` 增加 `parent_id` 列；embedding 只建在子块上。
- 新增 `adaptive` 模式：短文档单块、中文文档按句号聚合、代码文档按函数边界（本期可只做前两者）。

### 3.2 检索行为变化

- `retriever.py` 召回子块 → `rag_service.py` 组装上下文时向上取父块并去重（同一父块多个子块命中时只保留一个，得分取 max）。
- 引用位置标注到子块（页码/标题锚点），展示用父块。

### 3.3 验收标准

- 30 页 PDF 提问文档后部细节，召回的上下文包含完整章节而非孤立片段。
- chunker 单测覆盖：标题边界、超长段落、无结构纯文本、中英混排。
- 提供 `POST /api/knowledge/documents/{id}/rechunk` 重新切片接口（仿 WeKnora 的 reparse + process_config）。

---

## 4. Phase 3 —— 检索与重排：可插拔 + 真索引（对应差距 #3/#4/#5）

### 4.1 向量检索性能（先解决"能搜"再解决"搜得好"）

- 引入 **sqlite-vec**（单文件扩展，无新服务依赖）替代 Python 全表遍历：
  - `sqlite_repository.py` 的 `chunk_embeddings` 表改用 sqlite-vec 虚表；
  - 保留 JSON 列做迁移兼容，启动时自动迁移存量数据。
- 数据量超过 5 万 chunk 或需要多机时再评估 pgvector（在 `agent.yaml` 留 provider 配置位，本期不实现）。

### 4.2 检索策略重构 `retriever.py`

```
HybridRetriever
├── KeywordRetriever   # 升级为 BM25（rank-bm25 包 + jieba 分词替换 CJK-bigram）
├── VectorRetriever    # sqlite-vec 余弦
└── GraphRetriever     # 实体命中 -> 一跳邻居扩展（复用现有图谱表）
```

- 每路独立打分归一化后加权融合（RRF 起步），权重/最终 top-k/相关度阈值进 `agent.yaml`（保留现在 `hybrid/5/0.2` 的默认值语义）。
- 各路召回数量与耗时记入检索 trace（供前端进度与后续评测用）。

### 4.3 重排 Provider 化（替换 prompt 打分）

- 新建 `knowledge/reranking/`：
  - `base.py`：`Reranker` 协议（`rerank(query, candidates, top_k) -> list[ScoredCandidate]`）。
  - `ollama_reranker.py`：调用 Ollama 的 bge-reranker 类模型（`/api/embeddings` 或原生 rerank 端点）——**替代**现在的 `OllamaReranker` prompt 打分实现。
  - `api_reranker.py`：OpenAI 兼容 / Jina / 硅基流动等 HTTP rerank API。
  - `noop.py`：不启用时直接透传。
- `agent.yaml` 示例：

```yaml
knowledge:
  rerank:
    provider: ollama        # ollama | api | none
    model: bge-reranker-v2-m3
    top_k: 5
```

### 4.4 验收标准

- 5 万 chunk 库上向量检索 P95 < 100ms（现状全表遍历预计秒级）。
- 构造 20 条中文查询的小评测集，对比"有/无 rerank"的 top-5 命中率，rerank 开启后命中数不降且案例可解释。
- rerank 失败（模型不可用）自动降级为不重排并在 trace 标注，不阻塞回答。

---

## 5. Phase 4 —— 图谱检索补强（对应差距 #4 的 Graph 路）

Iris 已有实体抽取与可视化（`knowledge/extractor.py` + 前端图谱页），本期只补"检索时用得上"：

- `GraphRetriever`：查询词经现有 `_ENTITY_ALIASES` 归一后命中实体节点，取该节点相关 relation 所在的 chunk 进入候选池。
- 抽取 prompt 保持现 JSON 约定（可对照 `WeKnora-main/config/prompt_templates/` 微调实体类型定义）。
- 暂不做 WeKnora 式社区摘要/多跳（个人数据量收益低），图谱 UI 的实体编辑/合并能力已具备，不动。

---

## 6. Phase 5 —— 对话页面改版（对齐 WeKnora 聊天体验）

**参照**：WeKnora 前端 `frontend/src/components/chat/`（Vue）——Iris 用 React 重写交互形态，不搬代码。Iris 现有基础：`web-react/src/components/assistant-ui/`。

### 6.1 消息区改造

1. **气泡式布局**：用户右侧紧凑气泡、AI 左侧全宽卡片（现有工具卡片、思考过程折叠进 AI 卡片内，参照 WeKnora 的折叠设计）。
2. **inline 引用 popover**：正文中的 `[1]` 上标可点击，浮层显示 chunk 原文 + 来源文档名 + 置信度；数据来自现有流式协议中补充的 `citations` 字段。
3. **引用/来源抽屉**：回答卡片底部"引用 N 篇"横条，点开右侧抽屉，区分"知识库 / 网页"两个 tab（WeKnora references drawer 的形态）。
4. **RAG 管线进度**：`POST /api/chat/stream` 事件流新增 `pipeline_stage` 事件（`parsing → retrieval → rerank → generation`，数据来自 4.2 的检索 trace），前端在 AI 卡片顶部显示阶段进度条——这是 WeKnora 标志性的"过程可见"体验。
5. **流式 Markdown**：接入 mermaid 渲染（Iris 已有 UML 页可复用渲染器）与表格/代码高亮；回答完成后提供**复制 Markdown / 导出 .md** 操作。

### 6.2 输入区与回答后动作

- 回答完成自动生成 3 条**追问建议**（复用知识库召回结果的 cheap prompt，超时 2s 自动放弃）。
- 输入区保留现有的知识库选择器 + 附件上传，样式对齐 WeKnora 的紧凑设计。

### 6.3 流式协议变更（后端配合）

`api/app.py` 的 NDJSON 事件在现有 `text_delta/tool_started/tool_finished/message_completed/error` 基础上新增：

```jsonc
{"type": "pipeline_stage", "stage": "rerank", "detail": {"candidates": 20, "took_ms": 340}}
{"type": "citations", "items": [{"index": 1, "chunk_id": "...", "document": "...", "snippet": "...", "score": 0.87}]}
```

旧事件全部保留，前端按能力探测渲染。

### 6.4 验收标准

- 前端 Vitest 覆盖：引用 popover 开合、管线进度事件驱动渲染、追问建议降级（不出现则隐藏）。
- 手工走查：上传 PDF → 提问 → 全程可见阶段进度 → 点击引用看到原文 → 抽屉区分来源 → 导出 Markdown 成功。

---

## 7. Phase 6 —— 知识库管理页补齐（可选收尾）

按性价比排序，前两项建议做：

1. **召回测试台**：输入测试问题 → 展示各路召回得分明细（关键词/向量/图谱/rerank）——这是调试 Phase 3/4 的必备工具，也是 WeKnora "E2E Testing" 的简化版。
2. **chunk 在线编辑**：列表内编辑 chunk 文本 → 重新计算该条 embedding → 记录修订（SQLite 加 `chunk_revisions` 表，简单 diff 即可）。
3. 文件夹树与批量重解析：收益一般，视进度取舍。

---

## 8. 里程碑与顺序

| 里程碑 | 内容 | 依赖 |
|--------|------|------|
| M1 | Phase 1 解析层 + Phase 2 切片 | 无 |
| M2 | Phase 3 检索/重排（含 sqlite-vec） | M1（子块入库） |
| M3 | Phase 5 对话页面（引用/进度/建议） | M2 的 citations 与 trace 数据 |
| M4 | Phase 4 图谱检索 + Phase 6 管理页 | M2 |

Phase 5 前置到 Phase 4 之前，因为对话页面是用户明确要的体验目标，且它依赖的只是 M2 的数据结构而非图谱能力。

## 9. 风险与对策

- **本地模型可用性**：rerank/VLM/图谱抽取都依赖 Ollama，务必保持现有"受控降级"模式（失败→跳过该环节并在 trace 标注），不要让某个本地组件挂掉阻塞整个回答。
- **SQLite 并发写**：sqlite-vec 迁移与 chunk 编辑写入集中在后台任务队列（复用 `iris_agent/task_queue/`）执行，避免与聊天请求争锁。
- **前端改动面大**：assistant-ui 组件按 6.1 的 5 个点逐个小步替换，每步跑 Vitest，避免一次性重写 `App.tsx` 状态层。
- **评测先行**：Phase 3 动检索核心前，先固定一套 20–30 条查询的黄金评测集（含期望命中的 chunk），此后每次改动跑一遍，防止"重构后效果悄悄变差"。
