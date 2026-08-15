from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import Message, ProviderResponse
from iris_agent.session_search.service import SessionSearchService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("项目讨论")
    sessions.append(session.id, Message(role="user", content="聊聊项目进展"))
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    search = SessionSearchService(sessions)
    return TestClient(create_app(agent, sessions, search=search)), search


def test_search_api_returns_hits(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/api/search", params={"query": "项目"})

    assert response.status_code == 200
    hits = response.json()["hits"]
    assert len(hits) >= 1
    assert hits[0]["content"] == "聊聊项目进展"


def test_search_api_requires_query(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/api/search")

    assert response.status_code == 422


def test_search_api_respects_limit(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/api/search", params={"query": "项目", "limit": 1})

    assert response.status_code == 200
    assert len(response.json()["hits"]) <= 1
