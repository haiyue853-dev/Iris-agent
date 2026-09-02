from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


class RuntimeKnowledge:
    def model_runtime(self):
        return {"config": {"embedding_enabled": True}, "components": []}

    def update_model_runtime(self, payload):
        return {"config": payload, "components": [], "requires_reindex": True}

    def test_model_runtime(self, component=None):
        return {"components": [{"key": component or "embedding", "status": "connected"}]}

    def index_progress(self):
        return {"items": [{"document_id": "doc-1", "stage": "embedding", "message": "正在生成向量"}]}


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    return TestClient(create_app(agent, sessions, knowledge=RuntimeKnowledge()))


def test_knowledge_runtime_endpoints(tmp_path):
    client = _client(tmp_path)

    assert client.get("/api/knowledge/runtime").json()["config"]["embedding_enabled"] is True
    updated = client.patch("/api/knowledge/runtime", json={"embedding_enabled": False})
    assert updated.status_code == 200
    assert updated.json()["requires_reindex"] is True
    tested = client.post("/api/knowledge/runtime/test", json={"component": "reranker"})
    assert tested.status_code == 200
    assert tested.json()["components"][0]["key"] == "reranker"
    assert client.get("/api/knowledge/index-progress").json()["items"][0]["stage"] == "embedding"


def test_knowledge_runtime_rejects_invalid_update(tmp_path):
    response = _client(tmp_path).patch("/api/knowledge/runtime", json={"embedding_model": ""})

    assert response.status_code == 422
