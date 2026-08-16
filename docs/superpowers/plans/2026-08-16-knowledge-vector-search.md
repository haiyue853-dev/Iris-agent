# 知识库向量检索二期实现计划

日期：2026-08-16
分支：feature/knowledge-vector-search

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | OllamaEmbedder | `knowledge/embedder.py`（调 `/api/embed`，batch） |
| 2 | EmbeddingRetriever + 余弦相似度 | `knowledge/retriever.py`（向量缓存 + 排序） |
| 3 | HybridRetriever（RRF）+ 降级 | `knowledge/retriever.py` + `knowledge/service.py`（fallback） |
| 4 | 配置 + 装配 + 全量验证 | `settings.py` + `bootstrap.py` + `agent.yaml` |

## 任务细节

### 任务 1：OllamaEmbedder
- `EmbeddingError` 异常；`embed(texts) -> list[list[float]]`，httpx POST `/api/embed`，解析 `embeddings`。
- 测试：`tests/knowledge/test_embedder.py`（mock httpx，验证请求 body、解析、失败抛错）。

### 任务 2：EmbeddingRetriever
- 实现 `KnowledgeRetriever`；内存缓存 `entry_id -> (content_hash, vector)`；纯 Python 余弦相似度。
- 测试：`tests/knowledge/test_embedding_retriever.py`（fake embedder 返回确定性向量；验证命中、排序、缓存命中不重复 embed、截断）。

### 任务 3：HybridRetriever + 降级
- `HybridRetriever(keyword, embedding)`，RRF 融合（k=60）。
- `KnowledgeService` 加 `fallback_retriever` 参数，`search` 主失败时降级。
- 测试：`tests/knowledge/test_hybrid_retriever.py` + `tests/knowledge/test_service.py` 加降级用例。

### 任务 4：配置 + 装配 + 全量验证
- `KnowledgeSettings` 加 `retriever` / `embedding_model` / `embedding_base_url` / `embedding_timeout_seconds`。
- `bootstrap.py` 按 `retriever` 配置构造 keyword/embedding/hybrid，embedding/hybrid 时挂 keyword 为 fallback。
- `agent.yaml` 加配置节；后端全量 pytest + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖 embedder；任务 2 覆盖向量检索；任务 3 覆盖混合与降级；任务 4 覆盖配置装配。
- 类型一致性：`EmbeddingRetriever` / `HybridRetriever` 均实现 `KnowledgeRetriever`，`KnowledgeService.search` 接口不变。
- 安全边界：零新依赖；embedding 走本地 Ollama；降级 best-effort；余弦/RRF 纯函数无副作用。

## 前置条件（用户侧）

- 需要用户先 `ollama pull bge-m3`（或其它 embedding 模型），并以 `--embeddings` 重启 Ollama。未满足时，`retriever=keyword`（默认）不受影响；切到 embedding/hybrid 会自动降级回关键词检索。

## 执行结果（2026-08-16）

- 4 个任务全部完成并提交：OllamaEmbedder → EmbeddingRetriever → HybridRetriever+降级 → 配置装配。
- 提交链：`embedder` → `EmbeddingRetriever` → `HybridRetriever+降级` → `配置装配`。
- 验证：后端全量 **537 passed, 3 skipped, 0 failed**（新增 17 条向量检索测试）。
- 隐私核对：embedding 走本地 Ollama（数据不出本机）；降级 best-effort；余弦/RRF 纯函数无副作用；零新 pip 依赖（复用 httpx）。
