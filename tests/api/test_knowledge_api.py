"""Knowledge API tests: CRUD + search endpoints."""

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService
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
