# 知识库向量检索二期设计规格

日期：2026-08-16
分支：feature/knowledge-vector-search

## 1. 背景与目标

知识库一期（`feature/knowledge-base`，已合并）用**关键词检索**（`KeywordRetriever`，复用中文 bigram），检索器做成**可插拔**（`KnowledgeRetriever` Protocol）。

二期接入**本地 Ollama embedding**，加两种新检索器，并支持降级：

- `EmbeddingRetriever`：语义向量检索（纯向量）。
- `HybridRetriever`：关键词 + 向量融合（RRF）。

用户本地环境：Ollama 已装 `qwen3.5:4b`（chat 模型，用于回答）；检索需另拉 embedding 模型（推荐 `bge-m3`，中文效果好，约 1.2GB）。Ollama 服务当前**未开 `--embeddings`**，需重启加该参数。

## 2. 依赖

**零新 pip 依赖**：复用 `httpx`（调 Ollama）+ 纯 Python 余弦相似度。条目量级（几十~几百）纯 Python 点积毫秒级，无需 numpy / Chroma / FAISS。

## 3. 组件

### 3.1 `OllamaEmbedder`（`knowledge/embedder.py`）

| 方法 | 说明 |
|------|------|
| `embed(texts: list[str]) -> list[list[float]]` | 调 Ollama `/api/embed`，batch 返回向量 |

- 配置：`base_url`（默认 `http://localhost:11434`）、`model`（默认 `bge-m3`）、`timeout`。
- 用 `httpx.Client` POST `/api/embed`，body `{"model": ..., "input": texts}`，取 `embeddings` 数组。
- 失败（连接失败/模型不存在/未开 embeddings）抛 `EmbeddingError`。

### 3.2 `EmbeddingRetriever`（`knowledge/retriever.py`）

实现 `KnowledgeRetriever` 协议：

- `search(query, limit)`：
  1. `embed([query])` 得 query 向量。
  2. 对每个条目，从**内存缓存**取向量（key=`entry_id`，值=`(content_hash, vector)`）；缓存缺失或 content 变化则 `embed` 并缓存。
  3. 余弦相似度打分，按 `(-score, -updated_at)` 排序取前 `limit`。
- **内存缓存不持久化**：重启后重新 embed（几十条 batch embed 一次秒级），避免「持久化向量失效」的复杂度。
- 命中正文截断到 `max_hit_chars`。

### 3.3 `HybridRetriever`（`knowledge/retriever.py`）

- 内部持有 `KeywordRetriever` + `EmbeddingRetriever`。
- 分别取前 N 名，用 **RRF**（Reciprocal Rank Fusion）融合：`score = Σ 1/(k + rank)`，k=60。
- 返回融合排序后的命中（正文用关键词检索的原文截断）。

### 3.4 降级（`KnowledgeService.search`）

- `KnowledgeService` 增加可选 `fallback_retriever`。
- `search` 先试主 retriever；主 retriever 抛 `EmbeddingError`（或任何异常）时，降级到 `fallback_retriever`（关键词），保证知识库**始终可用**——Ollama 未拉模型/未开 embeddings 时自动退回关键词检索。

## 4. 配置

`agent.yaml` 的 `knowledge` 节新增：

| 键 | 默认 | 说明 |
|------|------|------|
| `retriever` | `keyword` | `keyword` / `embedding` / `hybrid` |
| `embedding_model` | `bge-m3` | Ollama embedding 模型名 |
| `embedding_base_url` | `http://localhost:11434` | Ollama 地址 |
| `embedding_timeout_seconds` | `60` | 调用超时 |

## 5. 一期不做

- 向量持久化（重启重新 embed）。
- 分块/切片（整条 embed，正文 ≤50000 字；超长由 Ollama 侧截断）。
- 多 embedding 源、重排（rerank）模型。
- 前端不变（检索是后端行为，`/api/knowledge/search` 接口不变）。

## 6. 隐私与安全

- embedding 走本地 Ollama，数据不出本机。
- 降级 best-effort，不因 embedding 失败影响知识库查询。
- 余弦/RRF 纯函数，无外部副作用。
