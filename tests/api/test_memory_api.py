from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    return TestClient(create_app(agent, sessions, memory=memory)), memory


def test_memory_crud_api(tmp_path):
    client, memory = _client(tmp_path)

    created = client.post("/api/memory", json={"content": "用户偏好中文", "category": "preference"})
    assert created.status_code == 201
    body = created.json()
    assert body["content"] == "用户偏好中文"
    assert body["category"] == "preference"

    listed = client.get("/api/memory")
    assert listed.status_code == 200
    assert listed.json()["entries"][0]["content"] == "用户偏好中文"

    assert client.delete(f"/api/memory/{body['id']}").status_code == 200
    assert client.get("/api/memory").json()["entries"] == []


def test_memory_api_rejects_invalid_category(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post("/api/memory", json={"content": "内容", "category": "unknown"})
    assert response.status_code == 422


def test_memory_api_rejects_blank_content(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post("/api/memory", json={"content": "", "category": "fact"})
    assert response.status_code == 422


def test_memory_api_delete_missing_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    assert client.delete("/api/memory/memory_missing").status_code == 404
