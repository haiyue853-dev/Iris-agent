from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    profile = ProfileService(ProfileRepository(tmp_path / "profile"), ProfileExtractor(Provider()))
    return TestClient(create_app(agent, sessions, profile=profile)), profile


def test_get_profile_returns_defaults(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/api/profile")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == ""
    assert data["preferences"] == []
    assert data["goals"] == []
    assert data["style"] == ""
    assert data["facts"] == []


def test_put_then_get_profile(tmp_path):
    client, _ = _client(tmp_path)

    response = client.put("/api/profile", json={"name": "小明", "preferences": ["简洁"], "facts": ["工程师"]})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "小明"
    assert data["preferences"] == ["简洁"]
    assert data["facts"] == ["工程师"]

    fetched = client.get("/api/profile").json()
    assert fetched["name"] == "小明"
    assert fetched["facts"] == ["工程师"]


def test_put_replaces_full_profile(tmp_path):
    client, _ = _client(tmp_path)

    client.put("/api/profile", json={"name": "小明", "facts": ["工程师"]})
    client.put("/api/profile", json={"name": "小红", "goals": ["构建 agent"]})

    data = client.get("/api/profile").json()
    assert data["name"] == "小红"
    assert data["facts"] == []
    assert data["goals"] == ["构建 agent"]


def test_put_truncates_items(tmp_path):
    client, profile = _client(tmp_path)
    profile.max_item_chars = 5

    client.put("/api/profile", json={"facts": ["这是一个很长的事实"]})

    assert client.get("/api/profile").json()["facts"] == ["这是一个很"]
