from __future__ import annotations

import time

import httpx
import pytest

from iris_agent.knowledge.embedder import EmbeddingError
from iris_agent.knowledge.parsing import ParsedDocument, ParsedSection
from iris_agent.knowledge.rag_service import RagKnowledgeService, RagSearchHit
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository, SqliteKnowledgeRepositoryError


class RecordingEmbedder:
    model = "test-embedding"

    def __init__(self, *, fail: bool = False, max_batch: int | None = None, max_chars: int | None = None) -> None:
        self.fail = fail
        self.max_batch = max_batch
        self.max_chars = max_chars
        self.calls: list[list[str]] = []

    def embed(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        if self.fail or (self.max_batch is not None and len(batch) > self.max_batch) or (
            self.max_chars is not None and any(len(text) > self.max_chars for text in batch)
        ):
            raise EmbeddingError("embedding unavailable")
        return [[1.0, float(index + 1)] for index, _ in enumerate(batch)]


class RecordingSemanticSplitter:
    def __init__(self):
        self.calls = []

    def split(self, title, text, *, target_chars):
        self.calls.append((title, text, target_chars))
        from iris_agent.knowledge.chunker import ChunkDraft
        return [ChunkDraft("本地语义片段", None)]


def make_service(tmp_path, *, embedder=None, **overrides) -> RagKnowledgeService:
    options = {
        "files_directory": tmp_path / "files",
        "chunk_target_chars": 20,
        "chunk_overlap_chars": 0,
        "embedding_batch_size": 2,
        "retrieval_limit": 5,
        "max_context_chars": 6000,
        "minimum_relevance_score": 0.2,
        "max_file_bytes": 10_000,
        "max_total_bytes": 100_000,
        "max_document_count": 100,
        "allowed_extensions": (".txt",),
    }
    options.update(overrides)
    return RagKnowledgeService(
        SqliteKnowledgeRepository(tmp_path / "knowledge.db"),
        embedder=embedder,
        **options,
    )


def test_local_semantic_splitter_is_used_for_uploaded_documents(tmp_path):
    splitter = RecordingSemanticSplitter()
    service = make_service(tmp_path, semantic_splitter=splitter)
    try:
        document = service.enqueue_upload("本地拆分", "source.txt", b"raw content")
        assert wait_for_terminal_status(service, document.id).status == "ready"
        assert splitter.calls and splitter.calls[0][0] == "本地拆分"
        assert [chunk.content for chunk in service.repository.chunks_for_document(document.id)] == ["本地语义片段"]
    finally:
        service.close()


def runtime_config(**overrides):
    values = {
        "embedding_enabled": False,
        "embedding_model": "bge-m3",
        "embedding_base_url": "http://localhost:11434",
        "semantic_split_enabled": False,
        "semantic_split_model": "bge-m3",
        "semantic_split_base_url": "http://localhost:11434",
        "graph_enabled": False,
        "graph_model": "deepseek-r1:8b",
        "graph_base_url": "http://localhost:11434",
        "image_enabled": False,
        "image_model": "qwen2.5vl:7b",
        "image_base_url": "http://localhost:11434",
        "reranker_enabled": False,
        "reranker_provider": "none",
        "reranker_model": "deepseek-r1:8b",
        "reranker_base_url": "http://localhost:11434",
    }
    values.update(overrides)
    return values


def wait_for_terminal_status(service: RagKnowledgeService, document_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        document = service.get_document(document_id)
        if document is not None and document.status in {"ready", "failed"}:
            return document
        time.sleep(0.01)
    raise AssertionError("knowledge indexing did not finish")


def test_enqueue_upload_enforces_document_quota_before_writing_file(tmp_path):
    service = make_service(tmp_path, max_document_count=1)
    try:
        service.enqueue_text("first", "first document")

        with pytest.raises(ValueError, match="数量已达上限"):
            service.enqueue_upload("second", "second.txt", b"second document")

        assert len(service.list_documents()) == 1
        assert list((tmp_path / "files").glob("*")) == []
    finally:
        service.close()


def test_enqueue_upload_enforces_total_size_quota(tmp_path):
    service = make_service(tmp_path, max_total_bytes=3)
    try:
        with pytest.raises(ValueError, match="总大小已达上限"):
            service.enqueue_upload("too large", "large.txt", b"1234")

        assert service.list_documents() == []
        assert list((tmp_path / "files").glob("*")) == []
    finally:
        service.close()


def test_update_text_rejects_content_that_exceeds_total_size_quota(tmp_path):
    service = make_service(tmp_path, max_total_bytes=10)
    try:
        document = service.add_text("small", "123")

        with pytest.raises(ValueError, match="总大小已达上限"):
            service.update_text_document(document.id, "large", "12345678901")

        assert service.repository.chunks_for_document(document.id)[0].content == "123"
    finally:
        service.close()


def test_delete_document_removes_persisted_upload(tmp_path):
    service = make_service(tmp_path)
    try:
        document = service.enqueue_upload("source", "source.txt", b"searchable source text")
        wait_for_terminal_status(service, document.id)
        source_files = list((tmp_path / "files").glob(f"{document.id}.*"))
        assert len(source_files) == 1

        assert service.delete_document(document.id) is True

        assert not source_files[0].exists()
    finally:
        service.close()


def test_upload_indexing_preserves_each_parsed_section_location(tmp_path, monkeypatch):
    service = make_service(tmp_path, allowed_extensions=(".pdf",), chunk_target_chars=100)
    monkeypatch.setattr(
        "iris_agent.knowledge.rag_service.parse_document",
        lambda *_args, **_kwargs: ParsedDocument((
            ParsedSection("第一页的独立内容。", location="第 1 页"),
            ParsedSection("第二页的独立内容。", location="第 2 页"),
        )),
    )
    try:
        document = service.enqueue_upload("分页资料", "source.pdf", b"mock pdf")

        assert wait_for_terminal_status(service, document.id).status == "ready"
        chunks = service.repository.chunks_for_document(document.id)

        assert [(chunk.content, chunk.location) for chunk in chunks] == [
            ("第一页的独立内容。", "第 1 页"),
            ("第二页的独立内容。", "第 2 页"),
        ]
    finally:
        service.close()


def test_search_diversifies_near_duplicate_results(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        service.add_text(
            "重复资料 A",
            "Vector search combines semantic embeddings and document ranking. "
            "Vector search combines semantic embeddings and document ranking.",
        )
        service.add_text(
            "重复资料 B",
            "Vector search combines semantic embeddings and document ranking. "
            "Vector search combines semantic embeddings and document ranking with extra details.",
        )
        service.add_text("互补资料", "Vector search can complement keyword retrieval using an inverted index.")

        hits = service.search("vector search", limit=2)

        assert [hit.title for hit in hits] == ["重复资料 A", "互补资料"]
    finally:
        service.close()


def test_collection_retrieval_config_overrides_default_top_k(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000, retrieval_limit=5)
    try:
        collection = service.create_collection("项目资料")
        service.add_text("RAG 基础", "RAG retrieval augments generation with relevant documents.", collection_id=collection.id)
        service.add_text("RAG 评估", "RAG evaluation measures retrieval quality and grounded answers.", collection_id=collection.id)
        service.update_collection_retrieval_config(collection.id, {"top_k": 1})

        hits = service.search("RAG", collection_id=collection.id)

        assert len(hits) == 1
    finally:
        service.close()


def test_debug_search_exposes_each_retrieval_stage_and_final_rank(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        document = service.add_text("RAG 调试", "混合检索使用关键词召回与向量召回，再进行融合排序。")

        trace = service.debug_search("关键词召回", limit=5, collection_id="collection-general")

        assert trace["query"] == "关键词召回"
        assert trace["candidate_limit"] == 15
        assert trace["elapsed_ms"] >= 0
        assert all(stage["elapsed_ms"] >= 0 for stage in trace["stages"])
        assert [stage["key"] for stage in trace["stages"]] == [
            "keyword", "graph", "vector", "fused", "reranked", "final",
        ]
        keyword = trace["stages"][0]["candidates"]
        final = trace["stages"][-1]["candidates"]
        assert keyword[0]["document_id"] == document.id
        assert keyword[0]["rank"] == 1
        assert final[0]["chunk_id"] == keyword[0]["chunk_id"]
        assert final[0]["routes"] == ["keyword"]
        assert trace["hits"][0]["chunk_id"] == final[0]["chunk_id"]
    finally:
        service.close()


def test_successful_rerank_keeps_unscored_candidates_out_of_final_mmr_pool(tmp_path):
    class LowScoreReranker:
        def score(self, query, candidates):
            return {candidate_id: 0.05 for candidate_id, _ in candidates}

        def close(self):
            return None

    service = make_service(
        tmp_path,
        chunk_target_chars=1000,
        reranker=LowScoreReranker(),
        reranker_candidates=2,
        model_config=runtime_config(
            reranker_enabled=True,
            reranker_provider="ollama",
            reranker_model="test-reranker",
        ),
    )
    try:
        service.add_text("资料一", "RAG 检索排序资料一")
        service.add_text("资料二", "RAG 检索排序资料二")
        service.add_text("资料三", "RAG 检索排序资料三")

        hits = service.search("RAG 检索排序", limit=3, collection_id="collection-general")

        assert len(hits) == 2
        assert all(hit.reranker_score is not None for hit in hits)
    finally:
        service.close()


def test_search_uses_expanded_query_for_recall_but_preserves_original_in_trace(tmp_path):
    embedder = RecordingEmbedder()
    service = make_service(tmp_path, embedder=embedder, chunk_target_chars=1000)
    query = "资料明明已经删掉了，为什么还会搜出旧答案？这种脏召回怎么处理？"
    try:
        trace = service.debug_search(query, limit=5, collection_id="collection-general")

        assert trace["query"] == query
        assert "文档删除" in trace["retrieval_query"]
        assert "向量库实时一致性" in trace["retrieval_query"]
        assert embedder.calls[-1] == [trace["retrieval_query"]]
    finally:
        service.close()


def test_global_search_routes_named_query_to_matching_collection(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        product = service.create_collection("产品资料")
        engineering = service.create_collection("技术资料")
        service.add_text("产品路线图", "产品研发将在第三季度发布新的路线图。", collection_id=product.id)
        service.add_text("技术路线图", "产品研发需要评估新的数据库架构。", collection_id=engineering.id)

        hits = service.search("产品研发路线图")

        assert [hit.collection_id for hit in hits] == [product.id]
        assert hits[0].collection_name == "产品资料"
    finally:
        service.close()


def test_global_context_citations_include_routed_collection_name(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        collection = service.create_collection("客户资料")
        service.add_text("客户交付", "客户交付计划将在下周完成验收。", collection_id=collection.id)

        _, citations = service.context_for("客户交付计划")

        assert citations[0]["collection_id"] == collection.id
        assert citations[0]["collection_name"] == "客户资料"
    finally:
        service.close()


def test_collection_evaluation_suggests_more_candidates_when_recall_is_low(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        collection = service.create_collection("项目资料")
        service.add_text("发布计划", "第三季度发布计划已经确认。", collection_id=collection.id)

        evaluation = service.evaluate_queries([], collection.id, [{
            "question": "第三季度发布计划",
            "expected_title": "不存在的资料",
        }])

        assert evaluation["collection_id"] == collection.id
        assert evaluation["recommendations"] == [{
            "field": "candidate_multiplier",
            "current": 3,
            "suggested": 4,
            "reason": "Hit@3 偏低，扩大候选集以减少漏召回。",
        }]
    finally:
        service.close()


def test_collection_evaluation_counts_expected_document_id_as_judged(tmp_path):
    service = make_service(tmp_path)
    try:
        service.search = lambda query, limit=None, collection_id=None: [
            RagSearchHit("document-1", "chunk-1", "发布计划", "第三季度发布", None, 0.9)
        ]

        evaluation = service.evaluate_queries([], None, [{
            "question": "什么时候发布？",
            "expected_document_id": "document-1",
        }])

        assert evaluation["judged_total"] == 1
        assert evaluation["metrics"]["hit_rate"]["1"] == 1.0
        assert evaluation["metrics"]["recall"]["1"] == 1.0
    finally:
        service.close()


def test_collection_evaluation_computes_chunk_level_metrics_at_requested_k(tmp_path):
    service = make_service(tmp_path)
    try:
        ranked_hits = [
            RagSearchHit("document-x", "chunk-x", "干扰资料", "无关", None, 0.9),
            RagSearchHit("document-1", "chunk-1", "目标资料一", "答案一", None, 0.8),
            RagSearchHit("document-2", "chunk-2", "目标资料二", "答案二", None, 0.7),
            RagSearchHit("document-y", "chunk-y", "另一干扰资料", "无关", None, 0.6),
        ]
        service.search = lambda query, limit=None, collection_id=None: ranked_hits[:limit]

        evaluation = service.evaluate_queries([], None, [{
            "question": "目标答案是什么？",
            "relevant_chunk_ids": ["chunk-1", "chunk-2"],
        }], k_values=[1, 3])

        assert evaluation["metrics"]["hit_rate"] == {"1": 0.0, "3": 1.0}
        assert evaluation["metrics"]["recall"] == {"1": 0.0, "3": 1.0}
        assert evaluation["metrics"]["precision"] == {"1": 0.0, "3": 0.667}
        assert evaluation["metrics"]["ndcg"] == {"1": 0.0, "3": 0.693}
        assert evaluation["metrics"]["mrr"] == 0.5
        assert evaluation["results"][0]["relevant_chunk_ids"] == ["chunk-1", "chunk-2"]
    finally:
        service.close()


def test_evaluation_case_validation_finds_duplicates_empty_annotations_and_stale_chunks(tmp_path):
    service = make_service(tmp_path)
    try:
        document = service.add_text("发布计划", "第三季度发布计划已经确认。", collection_id="collection-general")
        chunk_id = service.repository.chunks_for_document(document.id)[0].id

        result = service.validate_evaluation_cases([
            {"question": "什么时候发布？", "relevant_chunk_ids": [chunk_id, "chunk-missing"]},
            {"question": " 什么时候发布？ ", "expected_title": "发布计划"},
            {"question": "负责人是谁？"},
        ], "collection-general")

        assert result["summary"] == {"total": 3, "annotated": 2, "duplicates": 2, "empty_annotations": 1, "invalid_chunks": 1}
        assert result["rows"][0]["duplicate"] is True
        assert result["rows"][0]["invalid_chunk_ids"] == ["chunk-missing"]
        assert result["rows"][1]["duplicate"] is True
        assert result["rows"][2]["empty_annotation"] is True
    finally:
        service.close()


def test_chunk_edit_reembeds_only_the_changed_chunk_and_can_restore_it(tmp_path):
    embedder = RecordingEmbedder()
    service = make_service(tmp_path, embedder=embedder)
    try:
        document = service.add_text("发布计划", "原始切片内容")
        chunk = service.repository.chunks_for_document(document.id)[0]
        embedder.calls.clear()

        updated = service.update_chunk(chunk.id, "修正后的切片内容", "人工修订")

        assert updated["chunk"]["id"] == chunk.id
        assert updated["chunk"]["content"] == "修正后的切片内容"
        assert embedder.calls == [["修正后的切片内容"]]
        assert service.repository.embedding_count(document.id) == 1
        revision_id = updated["revisions"][0]["id"]

        restored = service.restore_chunk_revision(chunk.id, revision_id)
        assert restored["chunk"]["id"] == chunk.id
        assert restored["chunk"]["content"] == "原始切片内容"
        assert embedder.calls[-1] == ["原始切片内容"]
    finally:
        service.close()


def test_indexing_uses_configured_embedding_batch_size(tmp_path):
    embedder = RecordingEmbedder()
    service = make_service(tmp_path, embedder=embedder, chunk_target_chars=5, embedding_batch_size=2)
    try:
        document = service.enqueue_text("batched", "abcdefghijklmno")
        assert wait_for_terminal_status(service, document.id).status == "ready"

        assert [len(batch) for batch in embedder.calls] == [2, 1]
        assert service.repository.embedding_count(document.id) == 3
    finally:
        service.close()


def test_parent_child_indexing_embeds_only_children_and_keeps_parent_context(tmp_path):
    embedder = RecordingEmbedder()
    service = make_service(
        tmp_path,
        embedder=embedder,
        parent_chunk_target_chars=40,
        child_chunk_target_chars=10,
        child_chunk_overlap_chars=0,
    )
    try:
        document = service.enqueue_text("parent child", "abcdefghijklmnopqrstuvwx")
        assert wait_for_terminal_status(service, document.id).status == "ready"

        chunks = service.repository.chunks_for_document(document.id)
        parent_ids = {chunk.parent_id for chunk in chunks if chunk.parent_id is not None}
        children = [chunk for chunk in chunks if chunk.parent_id is not None]
        embedded_ids = {candidate.chunk_id for candidate in service.repository.embedding_candidates()}

        assert len(parent_ids) == 1
        assert len(children) == 3
        assert embedded_ids == {chunk.id for chunk in children}
        assert sum(len(batch) for batch in embedder.calls) == len(children)
    finally:
        service.close()


def test_vector_search_falls_back_to_cosine_scan_when_ann_is_unavailable(tmp_path, monkeypatch):
    service = make_service(tmp_path, embedder=RecordingEmbedder())
    try:
        document = service.add_text("vector fallback", "仅靠向量也能找到的正文")

        def unavailable(*_args, **_kwargs):
            raise SqliteKnowledgeRepositoryError("sqlite-vec unavailable")

        monkeypatch.setattr(service.repository, "embedding_search", unavailable)
        hits = service.search("completely different query")

        assert hits
        assert hits[0].document_id == document.id
        assert "vector" in hits[0].routes
    finally:
        service.close()


def test_index_progress_reports_completed_pipeline(tmp_path):
    service = make_service(tmp_path, embedder=RecordingEmbedder())
    try:
        document = service.enqueue_text("progress", "需要建立向量索引的正文")
        assert wait_for_terminal_status(service, document.id).status == "ready"

        progress = service.index_progress()["items"]

        assert next(item for item in progress if item["document_id"] == document.id)["stage"] == "completed"
    finally:
        service.close()


def test_index_progress_preserves_failed_stage_and_error(tmp_path):
    service = make_service(tmp_path, embedder=RecordingEmbedder(fail=True))
    try:
        document = service.enqueue_text("failed progress", "embedding backend unavailable")
        assert wait_for_terminal_status(service, document.id).status == "failed"

        progress = next(item for item in service.index_progress()["items"] if item["document_id"] == document.id)

        assert progress["stage"] == "failed"
        assert progress["failed_stage"] == "embedding"
        assert "embedding unavailable" in progress["message"]
    finally:
        service.close()


def test_runtime_model_update_applies_immediately_and_persists(tmp_path):
    path = tmp_path / "runtime.json"
    service = make_service(
        tmp_path,
        embedder=None,
        model_config=runtime_config(),
        runtime_config_path=path,
    )
    try:
        result = service.update_model_runtime({
            "embedding_enabled": True,
            "embedding_model": "nomic-embed-text",
        })

        assert service.embedder is not None
        assert service.embedder.model == "nomic-embed-text"
        assert result["config"]["embedding_enabled"] is True
        assert result["requires_reindex"] is True
        assert "nomic-embed-text" in path.read_text(encoding="utf-8")
    finally:
        service.close()


def test_runtime_model_health_checks_installed_ollama_model(tmp_path, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "bge-m3:latest"}]}

    monkeypatch.setattr("iris_agent.knowledge.rag_service.httpx.get", lambda *_args, **_kwargs: Response())
    service = make_service(
        tmp_path,
        embedder=RecordingEmbedder(),
        model_config=runtime_config(embedding_enabled=True),
        runtime_config_path=tmp_path / "runtime.json",
    )
    try:
        result = service.test_model_runtime("embedding")

        assert result["components"][0]["status"] == "connected"
        assert "已安装" in result["components"][0]["message"]
        assert service.model_runtime()["components"][0]["status"] == "connected"
    finally:
        service.close()


def test_runtime_reranker_health_requires_a_real_score(tmp_path, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen3.5:4b"}]}

    class RecordingReranker:
        model = "qwen3.5:4b"
        base_url = "http://localhost:11434"

        def __init__(self):
            self.calls = []

        def score(self, query, candidates):
            self.calls.append((query, candidates))
            return {"health": 0.9}

        def close(self):
            return None

    reranker = RecordingReranker()
    monkeypatch.setattr("iris_agent.knowledge.rag_service.httpx.get", lambda *_args, **_kwargs: Response())
    service = make_service(
        tmp_path,
        reranker=reranker,
        model_config=runtime_config(
            reranker_enabled=True, reranker_provider="ollama", reranker_model="qwen3.5:4b",
        ),
        runtime_config_path=tmp_path / "runtime.json",
    )
    try:
        result = service.test_model_runtime("reranker")

        assert result["components"][0]["status"] == "connected"
        assert reranker.calls == [("连接测试", [("health", "连接测试文档")])]
    finally:
        service.close()


def test_runtime_health_reuses_ollama_tags_for_components_on_same_server(tmp_path, monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "bge-m3"}, {"name": "deepseek-r1:8b"}]}

    def get(url, **_kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr("iris_agent.knowledge.rag_service.httpx.get", get)
    service = make_service(
        tmp_path,
        embedder=RecordingEmbedder(),
        model_config=runtime_config(embedding_enabled=True, graph_enabled=True),
        runtime_config_path=tmp_path / "runtime.json",
    )
    try:
        result = service.test_model_runtime()

        assert [item["status"] for item in result["components"][:2]] == ["connected", "connected"]
        assert calls == ["http://localhost:11434/api/tags"]
    finally:
        service.close()


def test_runtime_health_returns_readable_message_when_ollama_is_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "iris_agent.knowledge.rag_service.httpx.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("connection refused")),
    )
    service = make_service(
        tmp_path,
        embedder=RecordingEmbedder(),
        model_config=runtime_config(embedding_enabled=True),
        runtime_config_path=tmp_path / "runtime.json",
    )
    try:
        result = service.test_model_runtime("embedding")

        assert result["components"][0]["status"] == "failed"
        assert result["components"][0]["message"] == "无法连接 Ollama 服务，请确认服务已启动且地址正确"
    finally:
        service.close()


def test_indexing_splits_a_batch_when_embedding_backend_rejects_its_size(tmp_path):
    embedder = RecordingEmbedder(max_batch=2)
    service = make_service(tmp_path, embedder=embedder, chunk_target_chars=5, embedding_batch_size=4)
    try:
        document = service.enqueue_text("adaptive batch", "abcdefghijklmnopqrst")

        assert wait_for_terminal_status(service, document.id).status == "ready"
        assert [len(batch) for batch in embedder.calls] == [4, 2, 2]
        assert service.repository.embedding_count(document.id) == 4
    finally:
        service.close()


def test_indexing_pools_subvectors_when_one_chunk_exceeds_embedding_input_limit(tmp_path):
    embedder = RecordingEmbedder(max_chars=5)
    service = make_service(tmp_path, embedder=embedder, chunk_target_chars=20, embedding_batch_size=2)
    try:
        document = service.enqueue_text("long chunk", "abcdefghijklmnopqrst")

        assert wait_for_terminal_status(service, document.id).status == "ready"
        assert service.repository.embedding_count(document.id) == 1
        assert any(len(batch[0]) == 5 for batch in embedder.calls if len(batch) == 1)
    finally:
        service.close()


def test_embedding_failure_does_not_report_document_as_ready(tmp_path):
    service = make_service(tmp_path, embedder=RecordingEmbedder(fail=True))
    try:
        document = service.enqueue_text("degraded", "keyword fallback remains searchable")

        indexed = wait_for_terminal_status(service, document.id)

        assert indexed.status == "failed"
        assert "embedding unavailable" in (indexed.error_message or "")
        assert service.repository.keyword_search("fallback", 5)
    finally:
        service.close()


def test_context_applies_relevance_threshold_without_discarding_normal_hits(tmp_path):
    strict = make_service(tmp_path, minimum_relevance_score=0.9)
    try:
        strict.add_text("苹果", "苹果是一种水果")
        assert strict.context_for("苹果") == ("", [])
    finally:
        strict.close()

    normal_path = tmp_path / "normal"
    normal = make_service(normal_path, minimum_relevance_score=0.2)
    try:
        normal.add_text("苹果", "苹果是一种水果")
        context, citations = normal.context_for("苹果")
        assert "苹果是一种水果" in context
        assert citations
    finally:
        normal.close()


def test_global_graph_context_returns_citable_sources(tmp_path):
    service = make_service(tmp_path)
    try:
        document = service.add_text("果树知识", "苹果是一种水果。果树包含苹果。")

        context, citations = service.context_for("总结整体关系", mode="global")

        assert "知识图谱关系" in context
        assert citations
        assert all(item["document_id"] == document.id for item in citations)
        assert "[1]" in context
    finally:
        service.close()


def test_collection_evaluation_history_keeps_config_snapshot_and_restores_it(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        collection = service.create_collection("项目资料")
        service.add_text("发布计划", "第三季度发布计划已经确认。", collection_id=collection.id)

        service.evaluate_queries([], collection.id, [{
            "question": "第三季度发布计划",
            "expected_title": "发布计划",
        }])
        history = service.evaluation_history(collection.id)
        service.update_collection_retrieval_config(collection.id, {"candidate_multiplier": 5})
        restored = service.restore_evaluation_config(collection.id, history["items"][0]["id"])

        assert history["items"][0]["config"]["candidate_multiplier"] == 3
        assert history["items"][0]["recall_at_1"] == 1.0
        assert history["items"][0]["metrics"]["hit_rate"]["1"] == 1.0
        assert history["items"][0]["metrics"]["recall"]["3"] == 1.0
        assert restored["candidate_multiplier"] == 3
    finally:
        service.close()


def test_collection_evaluation_gate_marks_metrics_below_saved_thresholds(tmp_path):
    service = make_service(tmp_path, chunk_target_chars=1000)
    try:
        collection = service.create_collection("项目资料")
        service.add_text("发布计划", "第三季度发布计划已经确认。", collection_id=collection.id)
        saved = service.update_evaluation_gate(collection.id, {"recall_at_1": 1, "recall_at_3": 1, "mrr": 1})
        evaluation = service.evaluate_queries([], collection.id, [{"question": "不存在的问题", "expected_title": "发布计划"}])

        assert saved["recall_at_1"] == 1
        assert evaluation["quality_gate"]["passed"] is False
        assert {item["metric"] for item in evaluation["quality_gate"]["failures"]} == {"recall_at_1", "recall_at_3", "mrr"}
    finally:
        service.close()
