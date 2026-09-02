"""Knowledge API tests: CRUD + search endpoints."""

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KeywordRetriever
from iris_agent.knowledge.rag_service import RagKnowledgeService
from iris_agent.knowledge.service import KnowledgeService
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    repository = KnowledgeRepository(tmp_path / "knowledge")
    retriever = KeywordRetriever(repository.list, max_hit_chars=500)
    knowledge = KnowledgeService(repository, retriever)
    return TestClient(create_app(agent, sessions, knowledge=knowledge)), knowledge


def _rag_client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    knowledge = RagKnowledgeService(
        SqliteKnowledgeRepository(tmp_path / "knowledge.db"),
        embedder=None,
        files_directory=tmp_path / "files",
        chunk_target_chars=100,
        chunk_overlap_chars=0,
        embedding_batch_size=2,
        retrieval_limit=5,
        max_context_chars=6000,
        minimum_relevance_score=0.2,
        max_file_bytes=10_000,
        max_total_bytes=100_000,
        max_document_count=100,
        allowed_extensions=(".txt",),
    )
    return TestClient(create_app(agent, sessions, knowledge=knowledge)), knowledge


def test_add_knowledge_api(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post("/api/knowledge", json={"title": "多模态面试", "content": "多模态大模型结构"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "多模态面试"
    assert "content" not in data
    assert data["id"].startswith("kb-")


def test_list_knowledge_api(tmp_path):
    client, knowledge = _client(tmp_path)
    knowledge.add("a", "内容a")
    knowledge.add("b", "内容b")
    response = client.get("/api/knowledge")
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 2


def test_get_knowledge_api(tmp_path):
    client, knowledge = _client(tmp_path)
    entry = knowledge.add("多模态", "多模态大模型结构")
    response = client.get(f"/api/knowledge/{entry.id}")
    assert response.status_code == 200
    assert response.json()["content"] == "多模态大模型结构"


def test_get_knowledge_missing_404(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/knowledge/kb-ffffffffffff")
    assert response.status_code == 404


def test_delete_knowledge_api(tmp_path):
    client, knowledge = _client(tmp_path)
    entry = knowledge.add("a", "内容")
    response = client.delete(f"/api/knowledge/{entry.id}")
    assert response.status_code == 200
    assert knowledge.get(entry.id) is None


def test_delete_knowledge_missing_404(tmp_path):
    client, _ = _client(tmp_path)
    response = client.delete("/api/knowledge/kb-ffffffffffff")
    assert response.status_code == 404


def test_search_knowledge_api(tmp_path):
    client, knowledge = _client(tmp_path)
    knowledge.add("多模态面试", "多模态大模型结构")
    response = client.get("/api/knowledge/search", params={"query": "多模态"})
    assert response.status_code == 200
    assert len(response.json()["hits"]) == 1


def test_search_knowledge_api_requires_query(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/knowledge/search")
    assert response.status_code == 422


def test_debug_search_api_returns_pipeline_stages(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        knowledge.add_text("检索调试", "关键词检索与向量检索组成混合召回。")

        response = client.get("/api/knowledge/search/debug", params={"query": "关键词检索", "collection_id": "collection-general", "limit": 5})

        assert response.status_code == 200
        payload = response.json()
        assert payload["query"] == "关键词检索"
        assert payload["stages"][0]["key"] == "keyword"
        assert payload["stages"][-1]["key"] == "final"
        assert payload["hits"][0]["chunk_id"] == payload["stages"][-1]["candidates"][0]["chunk_id"]
    finally:
        knowledge.close()


def test_uploaded_source_api_serves_the_original_file_inline(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        document = knowledge.enqueue_upload("原始资料", "source.txt", b"original source text", "text/plain")

        response = client.get(f"/api/knowledge/{document.id}/source")

        assert response.status_code == 200
        assert response.content == b"original source text"
        assert response.headers["content-disposition"].startswith("inline")
    finally:
        knowledge.close()


def test_collection_retrieval_config_api_returns_saved_effective_values(tmp_path):
    client, _ = _rag_client(tmp_path)
    try:
        collection = client.post("/api/knowledge/collections", json={"name": "项目资料"}).json()

        updated = client.patch(f"/api/knowledge/collections/{collection['id']}/retrieval-config", json={
            "top_k": 3,
            "candidate_multiplier": 4,
            "minimum_relevance_score": 0.4,
            "mmr_relevance_weight": 0.55,
        })
        fetched = client.get(f"/api/knowledge/collections/{collection['id']}/retrieval-config")

        assert updated.status_code == 200
        assert updated.json()["config"] == {
            "top_k": 3,
            "candidate_multiplier": 4,
            "minimum_relevance_score": 0.4,
            "mmr_relevance_weight": 0.55,
        }
        assert fetched.json() == updated.json()
    finally:
        _.close()


def test_evaluation_history_api_restores_a_collection_strategy_snapshot(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        collection = client.post("/api/knowledge/collections", json={"name": "项目资料"}).json()
        knowledge.add_text("发布计划", "第三季度发布计划已经确认。", collection_id=collection["id"])

        evaluated = client.post("/api/knowledge/evaluate", json={
            "collection_id": collection["id"],
            "cases": [{"question": "第三季度发布计划", "expected_title": "发布计划"}],
        })
        history = client.get("/api/knowledge/evaluate/history", params={"collection_id": collection["id"]})
        client.patch(f"/api/knowledge/collections/{collection['id']}/retrieval-config", json={"candidate_multiplier": 5})
        restored = client.post(
            f"/api/knowledge/evaluate/history/{history.json()['items'][0]['id']}/restore",
            params={"collection_id": collection["id"]},
        )

        assert evaluated.status_code == 200
        assert history.status_code == 200
        assert history.json()["items"][0]["recall_at_1"] == 1.0
        assert restored.json()["config"]["candidate_multiplier"] == 3
    finally:
        knowledge.close()


def test_evaluation_api_accepts_large_chunk_level_suite_and_requested_k(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        collection = client.post("/api/knowledge/collections", json={"name": "项目资料"}).json()
        document = knowledge.add_text("发布计划", "第三季度发布计划已经确认。", collection_id=collection["id"])
        chunk_id = knowledge.repository.chunks_for_document(document.id)[0].id

        response = client.post("/api/knowledge/evaluate", json={
            "collection_id": collection["id"],
            "k_values": [1, 5],
            "cases": [{"question": "第三季度发布计划", "relevant_chunk_ids": [chunk_id]} for _ in range(31)],
        })

        assert response.status_code == 200
        assert response.json()["total"] == 31
        assert response.json()["metrics"]["k_values"] == [1, 5]
    finally:
        knowledge.close()


def test_evaluation_validation_api_reports_stale_chunk_ids(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        response = client.post("/api/knowledge/evaluate/validate", json={
            "collection_id": "collection-general",
            "cases": [{"question": "发布计划是什么？", "relevant_chunk_ids": ["chunk-missing"]}],
        })

        assert response.status_code == 200
        assert response.json()["summary"]["invalid_chunks"] == 1
        assert response.json()["rows"][0]["invalid_chunk_ids"] == ["chunk-missing"]
    finally:
        knowledge.close()


def test_chunk_edit_api_preserves_id_and_restores_revision(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        document = knowledge.add_text("发布计划", "原始切片内容")
        chunk = knowledge.repository.chunks_for_document(document.id)[0]

        updated = client.patch(f"/api/knowledge/{document.id}/chunks/{chunk.id}", json={"content": "修正后的内容", "location": "人工修订"})
        history = client.get(f"/api/knowledge/{document.id}/chunks/{chunk.id}/revisions")
        revision_id = history.json()["revisions"][0]["id"]
        restored = client.post(f"/api/knowledge/{document.id}/chunks/{chunk.id}/revisions/{revision_id}/restore")

        assert updated.status_code == 200
        assert updated.json()["chunk"]["id"] == chunk.id
        assert updated.json()["chunk"]["content"] == "修正后的内容"
        assert history.status_code == 200
        assert restored.json()["chunk"]["id"] == chunk.id
        assert restored.json()["chunk"]["content"] == "原始切片内容"
    finally:
        knowledge.close()


def test_evaluation_gate_api_saves_collection_thresholds(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        collection = client.post("/api/knowledge/collections", json={"name": "项目资料"}).json()
        updated = client.patch("/api/knowledge/evaluate/gate", params={"collection_id": collection["id"]}, json={"recall_at_1": 0.8, "recall_at_3": 0.9, "mrr": 0.85})
        fetched = client.get("/api/knowledge/evaluate/gate", params={"collection_id": collection["id"]})

        assert updated.status_code == 200
        assert fetched.json() == {"thresholds": {"recall_at_1": 0.8, "recall_at_3": 0.9, "mrr": 0.85}}
    finally:
        knowledge.close()


def test_bad_case_api_preserves_chunk_level_ground_truth(tmp_path):
    client, knowledge = _rag_client(tmp_path)
    try:
        created = client.post("/api/knowledge/bad-cases", json={
            "question": "发布计划在哪里？",
            "relevant_chunk_ids": ["chunk-1", "chunk-2"],
            "relevant_document_ids": ["document-1"],
        })

        assert created.status_code == 200
        assert created.json()["relevant_chunk_ids"] == ["chunk-1", "chunk-2"]
        assert client.get("/api/knowledge/bad-cases").json()["cases"][0]["relevant_document_ids"] == ["document-1"]
    finally:
        knowledge.close()
