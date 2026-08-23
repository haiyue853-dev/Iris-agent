# 本地 RAG 知识库实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Iris 知识库升级为基于本地 Ollama、SQLite FTS5 和持久化分块向量的文件 RAG，并在聊天中自动提供可追溯引用。

**架构：** 新增 SQLite 文档仓储保存资料、切片、FTS5 索引和 embedding；复用 `LocalAttachmentExtractor` 提取上传资料，复用 `OllamaEmbedder` 批量生成向量。`KnowledgeService` 暴露文档和检索上下文，`AgentService` 只将本轮命中的受控片段注入模型请求，引用随完成事件返回而不修改历史消息。

**技术栈：** Python 3.13、FastAPI、SQLite FTS5、httpx、Ollama `/api/embed`、React 19、Vitest、pytest。

---

## 文件结构

- 创建：`iris_agent/knowledge/documents.py` — 文档、分块、引用及索引状态领域模型。
- 创建：`iris_agent/knowledge/chunker.py` — 保持定位信息的中文分块器。
- 创建：`iris_agent/knowledge/sqlite_repository.py` — SQLite schema、迁移、FTS5、资料/分块/向量事务。
- 创建：`iris_agent/knowledge/rag_retriever.py` — FTS5 与 Ollama embedding 的 RRF 混合召回。
- 创建：`iris_agent/knowledge/ingestion.py` — 上传校验、受控文件保存、提取、批量向量化和恢复任务。
- 修改：`iris_agent/knowledge/service.py` — 文档生命周期、检索上下文、兼容旧知识 API。
- 修改：`iris_agent/config/settings.py`、`agent.yaml` — RAG 数据路径、额度、切片、召回和阈值配置。
- 修改：`iris_agent/bootstrap.py` — 构造、恢复和关闭新知识服务。
- 修改：`iris_agent/core/agent.py`、`iris_agent/core/models.py` — 聊天自动注入与 `message_completed` 引用事件。
- 修改：`iris_agent/api/knowledge_api.py`、`iris_agent/api/schemas.py` — 文档上传、状态、详情、删除与切片级搜索 API。
- 修改：`web-react/src/types.ts`、`web-react/src/api/knowledge.ts`、`web-react/src/components/knowledge/KnowledgePage.tsx`、`web-react/src/components/assistant-ui/thread.tsx`、`web-react/src/lib/irisRuntime.ts`、`web-react/src/App.css` — 资料库 UI 与聊天引用渲染。
- 创建测试：`tests/knowledge/test_chunker.py`、`test_sqlite_repository.py`、`test_ingestion.py`、`test_rag_retriever.py`、`tests/api/test_knowledge_documents.py`、`tests/core/test_agent_knowledge_context.py`。
- 修改测试：`tests/knowledge/test_service.py`、`tests/test_bootstrap.py`、`web-react/src/components/knowledge/KnowledgePage.test.tsx`、`web-react/src/lib/irisRuntime.parts.test.ts`。

### 任务 1：配置、领域模型和中文分块

**文件：**
- 创建：`iris_agent/knowledge/documents.py`、`iris_agent/knowledge/chunker.py`
- 修改：`iris_agent/config/settings.py`、`agent.yaml`
- 测试：`tests/knowledge/test_chunker.py`、`tests/config/test_settings.py`

- [ ] **步骤 1：编写失败的分块与配置测试**

```python
def test_chunker_preserves_page_location_and_overlap():
    chunks = chunk_text("甲。" * 700, location="第 3 页", target_chars=800, overlap_chars=120)
    assert len(chunks) >= 2
    assert all(chunk.location == "第 3 页" for chunk in chunks)
    assert chunks[0].content[-100:] in chunks[1].content

def test_default_knowledge_settings_enable_local_rag_paths(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")
    assert settings.knowledge.database_file == Path("data/knowledge/knowledge.db")
    assert settings.knowledge.embedding_model == "bge-m3"
    assert settings.knowledge.chunk_target_chars == 800
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_chunker.py tests/config/test_settings.py -q`

预期：FAIL，缺少 `chunk_text` 与 `KnowledgeSettings` 的 RAG 配置字段。

- [ ] **步骤 3：实现最小领域类型、分块器和配置**

```python
@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: str
    document_id: str
    ordinal: int
    content: str
    location: str | None
    content_hash: str

def chunk_text(text: str, *, location: str | None, target_chars: int, overlap_chars: int) -> list[ChunkDraft]:
    units = [unit.strip() for unit in re.split(r"(?<=[。！？\n])", text) if unit.strip()]
    chunks: list[ChunkDraft] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) > target_chars:
            chunks.append(ChunkDraft(content=current, location=location))
            current = current[-overlap_chars:] + unit
        else:
            current += unit
    if current:
        chunks.append(ChunkDraft(content=current, location=location))
    return chunks
```

向 `KnowledgeSettings` 添加 `database_file`、`files_directory`、单文件/总量/数量限制、`chunk_target_chars`、`chunk_overlap_chars`、`embedding_batch_size`、`retrieval_limit`、`max_context_chars`、`minimum_relevance_score`；`load_settings` 做非负、路径和范围验证。

- [ ] **步骤 4：运行测试确认通过**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_chunker.py tests/config/test_settings.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add iris_agent/knowledge/documents.py iris_agent/knowledge/chunker.py iris_agent/config/settings.py agent.yaml tests/knowledge/test_chunker.py tests/config/test_settings.py
git commit -m "feat: define local rag knowledge settings and chunks"
```

### 任务 2：SQLite 文档仓储与旧数据迁移

**文件：**
- 创建：`iris_agent/knowledge/sqlite_repository.py`
- 修改：`iris_agent/knowledge/repository.py`、`iris_agent/knowledge/service.py`
- 测试：`tests/knowledge/test_sqlite_repository.py`、`tests/knowledge/test_service.py`

- [ ] **步骤 1：编写失败的仓储测试**

```python
def test_save_document_indexes_chunks_and_cascades_delete(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = KnowledgeDocument.new("面经.pdf", source_type="upload", media_type="application/pdf")
    repository.save_document_with_chunks(document, [ChunkDraft("Transformer 注意力机制", "第 2 页")])
    assert repository.keyword_search("注意力", 5)[0].document_id == document.id
    repository.delete_document(document.id)
    assert repository.keyword_search("注意力", 5) == []

def test_json_migration_is_idempotent_and_preserves_source(tmp_path):
    legacy = KnowledgeRepository(tmp_path / "legacy")
    legacy.save(KnowledgeEntry.new("旧条目", "旧正文"))
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    assert repository.migrate_legacy(legacy) == 1
    assert repository.migrate_legacy(legacy) == 0
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_sqlite_repository.py -q`

预期：FAIL，缺少 `SqliteKnowledgeRepository`。

- [ ] **步骤 3：实现 schema、事务、FTS5 和迁移**

```sql
CREATE TABLE documents (id TEXT PRIMARY KEY, title TEXT NOT NULL, source_type TEXT NOT NULL, media_type TEXT, size_bytes INTEGER NOT NULL, original_name TEXT, status TEXT NOT NULL, error_message TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, content TEXT NOT NULL, location TEXT, content_hash TEXT NOT NULL, UNIQUE(document_id, ordinal));
CREATE TABLE chunk_embeddings (chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE, model TEXT NOT NULL, dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL, content_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, title, content);
```

所有写入使用 `BEGIN IMMEDIATE`；`save_document_with_chunks` 同时写 documents、chunks 和 FTS；`delete_document` 先删数据库关联记录再返回原文件清理标识。`migrate_legacy` 以 `legacy:<entry_id>` 保存来源键，迁移失败不删除 JSON。

- [ ] **步骤 4：运行仓储与旧服务测试确认通过**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_sqlite_repository.py tests/knowledge/test_service.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add iris_agent/knowledge/sqlite_repository.py iris_agent/knowledge/repository.py iris_agent/knowledge/service.py tests/knowledge/test_sqlite_repository.py tests/knowledge/test_service.py
git commit -m "feat: persist rag knowledge documents in sqlite"
```

### 任务 3：安全摄取、持久化向量和混合召回

**文件：**
- 创建：`iris_agent/knowledge/ingestion.py`、`iris_agent/knowledge/rag_retriever.py`
- 修改：`iris_agent/knowledge/embedder.py`、`iris_agent/knowledge/service.py`
- 测试：`tests/knowledge/test_ingestion.py`、`tests/knowledge/test_rag_retriever.py`

- [ ] **步骤 1：编写失败的摄取与检索测试**

```python
def test_ingest_pdf_marks_ready_and_persists_vectors(tmp_path, fake_embedder):
    service = make_ingestion_service(tmp_path, fake_embedder)
    document = service.ingest_upload("notes.md", b"Transformer attention context", "text/markdown")
    assert document.status == "ready"
    assert service.repository.embedding_count(document.id) > 0

def test_hybrid_search_fuses_keyword_and_vector_results(repository, fake_embedder):
    repository.save_document_with_chunks(KnowledgeDocument.new("notes.md", "upload", "text/markdown"), [ChunkDraft("Transformer attention", "第 2 页")])
    hits = HybridChunkRetriever(repository, fake_embedder).search("Transformer", limit=3)
    assert hits[0].location == "第 2 页"
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_ingestion.py tests/knowledge/test_rag_retriever.py -q`

预期：FAIL，缺少摄取服务和切片检索器。

- [ ] **步骤 3：实现安全上传、状态机和 RRF 检索**

```python
def ingest_upload(self, original_name: str, content: bytes, media_type: str) -> KnowledgeDocument:
    self._validate_upload(original_name, content, media_type)
    document = self._repository.create_queued_document(
        title=original_name,
        source_type="upload",
        media_type=media_type,
        size_bytes=len(content),
        original_name=original_name,
    )
    self._store.write(document.id, suffix, content)
    return self._index(document.id)

def search(self, query: str, limit: int) -> list[KnowledgeChunkHit]:
    keyword = self._repository.keyword_search(query, limit * 3)
    vector = self._vector_search(query, limit * 3)
    return reciprocal_rank_fusion(keyword, vector, limit)
```

复用 `LocalAttachmentExtractor`，将每个 `AttachmentExtractionSource.location` 传给分块器；批量调用 `OllamaEmbedder.embed`；向量写入只接受非空且同维结果。Ollama 错误将文档标为 `failed`，查询时仅降级 FTS5，不抛出未处理异常。

- [ ] **步骤 4：运行测试确认通过**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/knowledge/test_ingestion.py tests/knowledge/test_rag_retriever.py tests/knowledge/test_embedder.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add iris_agent/knowledge/ingestion.py iris_agent/knowledge/rag_retriever.py iris_agent/knowledge/embedder.py iris_agent/knowledge/service.py tests/knowledge/test_ingestion.py tests/knowledge/test_rag_retriever.py
git commit -m "feat: ingest and retrieve local rag knowledge"
```

### 任务 4：文档 API、启动恢复与聊天自动引用

**文件：**
- 修改：`iris_agent/bootstrap.py`、`iris_agent/core/agent.py`、`iris_agent/core/models.py`、`iris_agent/api/knowledge_api.py`、`iris_agent/api/schemas.py`、`iris_agent/api/app.py`
- 测试：`tests/api/test_knowledge_documents.py`、`tests/core/test_agent_knowledge_context.py`、`tests/test_bootstrap.py`

- [ ] **步骤 1：编写失败的 API 与聊天集成测试**

```python
def test_upload_returns_document_without_server_path(client):
    response = client.post("/api/knowledge/documents", files={"file": ("notes.md", b"RAG context", "text/markdown")})
    assert response.status_code == 201
    assert "file_path" not in response.json()

def test_relevant_question_injects_context_and_returns_citations(session_repo, provider):
    service = FakeKnowledgeService(hits=[_hit("doc-1", "第 3 页", "注意力机制")])
    agent = AgentService(loop=AgentLoop(provider, ToolRegistry()), sessions=session_repo, system_prompt="system", knowledge_service=service)
    events = list(agent.run("s1", "注意力机制怎么解释"))
    assert "[知识库参考资料]" in provider.messages[0][1].content
    assert events[-1].data["citations"] == [{"document_id": "doc-1", "location": "第 3 页"}]
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api/test_knowledge_documents.py tests/core/test_agent_knowledge_context.py tests/test_bootstrap.py -q`

预期：FAIL，缺少 documents API 与 `knowledge_service` 参数。

- [ ] **步骤 3：实现 API、恢复和受控注入**

```python
def _build_messages(self, session: Session, knowledge_context: KnowledgeContext | None = None) -> list[Message]:
    messages = [Message(role="system", content=self.system_prompt)]
    if knowledge_context is not None:
        messages.append(Message(role="system", content=knowledge_context.render_prompt()))
    messages.extend(session.messages)
    return messages

def run(self, session_id: str, user_message: str, attachment_ids: list[str] | None = None, is_cancelled: Callable[[], bool] | None = None):
    context = self.knowledge_service.context_for(user_message) if self.knowledge_service else None
    messages = self._build_messages(session, context)
    yield from self._run_loop(session_id, messages, self._registry_for(session_id), is_cancelled, citations=context.citations if context else [])
```

`KnowledgeContext` 只在分数达到阈值时创建，最大 6 个片段与 `max_context_chars`。`message_completed` 保持 `message_id`，新增 `citations` 数组；持久化的 assistant `Message` 不保存内部上下文。启动时调用 `recover_incomplete_documents()`，重新入队 queued/indexing 文档。

- [ ] **步骤 4：运行 API、聊天和全后端测试确认通过**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api/test_knowledge_documents.py tests/core/test_agent_knowledge_context.py tests/knowledge tests/test_bootstrap.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add iris_agent/bootstrap.py iris_agent/core/agent.py iris_agent/core/models.py iris_agent/api/knowledge_api.py iris_agent/api/schemas.py iris_agent/api/app.py tests/api/test_knowledge_documents.py tests/core/test_agent_knowledge_context.py tests/test_bootstrap.py
git commit -m "feat: cite local rag knowledge in chat"
```

### 任务 5：资料库界面和聊天引用渲染

**文件：**
- 修改：`web-react/src/types.ts`、`web-react/src/api/knowledge.ts`、`web-react/src/components/knowledge/KnowledgePage.tsx`、`web-react/src/lib/irisRuntime.ts`、`web-react/src/components/assistant-ui/thread.tsx`、`web-react/src/App.css`
- 测试：`web-react/src/components/knowledge/KnowledgePage.test.tsx`、`web-react/src/lib/irisRuntime.parts.test.ts`

- [ ] **步骤 1：编写失败的上传和引用测试**

```tsx
it('uploads a document and shows its indexing status', async () => {
  render(<KnowledgePage />);
  await userEvent.upload(screen.getByLabelText('上传资料'), new File(['内容'], 'notes.md', { type: 'text/markdown' }));
  expect(await screen.findByText('索引中')).toBeVisible();
});

it('maps message citations into a source part', () => {
  expect(toThreadMessages([{ role: 'assistant', content: '答案', citations: [{ document_id: 'doc-1', title: 'notes.md', location: '第 2 页' }] }])[0].content)
    .toContainEqual(expect.objectContaining({ type: 'source', title: 'notes.md（第 2 页）' }));
});
```

- [ ] **步骤 2：运行测试确认失败**

运行：`npm.cmd test -- --run src/components/knowledge/KnowledgePage.test.tsx src/lib/irisRuntime.parts.test.ts`

预期：FAIL，缺少上传控件与 citations 映射。

- [ ] **步骤 3：实现 API 客户端、资料页面和引用映射**

```ts
export async function uploadKnowledgeDocument(file: File): Promise<KnowledgeDocument> {
  const body = new FormData();
  body.append('file', file);
  return request<KnowledgeDocument>('/api/knowledge/documents', { method: 'POST', body });
}
```

资料页显示文件名、类型、大小、索引状态、错误摘要、上传和删除；搜索结果显示切片文本与定位。`irisRuntime` 从完成事件收集 citations 并转换为 assistant-ui `source` part；Thread 使用既有 source 渲染器，点击 source 带 `document_id` 跳转到知识库详情。CSS 使用现有 `--iris-*` 变量，窄屏保持单列。

- [ ] **步骤 4：运行前端测试与构建确认通过**

运行：`npm.cmd test -- --run && npm.cmd run build`

预期：所有 Vitest 测试 PASS，TypeScript 与 Vite 构建 exit 0。

- [ ] **步骤 5：提交**

```bash
git add web-react/src/types.ts web-react/src/api/knowledge.ts web-react/src/components/knowledge/KnowledgePage.tsx web-react/src/lib/irisRuntime.ts web-react/src/components/assistant-ui/thread.tsx web-react/src/App.css web-react/src/components/knowledge/KnowledgePage.test.tsx web-react/src/lib/irisRuntime.parts.test.ts
git commit -m "feat: add local rag knowledge workspace"
```

### 任务 6：端到端验证和运维说明

**文件：**
- 修改：`README.md`
- 创建：`docs/features/local-rag-knowledge-base.md`
- 测试：现有后端和前端全量套件

- [ ] **步骤 1：添加失败的配置文档检查**

```python
def test_readme_documents_local_ollama_knowledge_requirements():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'ollama pull bge-m3' in text
    assert '知识库' in text
```

- [ ] **步骤 2：运行测试确认失败**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/config/test_readme.py -q`

预期：FAIL，README 尚未说明本地 RAG 前置条件。

- [ ] **步骤 3：写入运行、隐私和恢复说明**

文档必须列出 `ollama pull bge-m3`、支持格式、数据目录、状态含义、Ollama 不可用时的关键词降级、删除行为、扫描 PDF 的限制以及如何重建索引；不记录 API key 或本地绝对路径。

- [ ] **步骤 4：运行全量验证**

运行：

```bash
D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -q
cd web-react && npm.cmd test -- --run && npm.cmd run build
```

预期：pytest、Vitest 与前端构建均 exit 0。

- [ ] **步骤 5：提交**

```bash
git add README.md docs/features/local-rag-knowledge-base.md tests/config/test_readme.py
git commit -m "docs: explain local rag knowledge base"
```
