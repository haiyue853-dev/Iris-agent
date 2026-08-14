from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def _client(tmp_path) -> TestClient:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(OpenAICompatibleProvider(object(), "test"), ToolRegistry(), 4), sessions, "test")
    radar = HotRadarService(tmp_path / "radar", sources={"tech": lambda: [{"title": "AI 新进展", "url": "https://example.test/ai", "source": "Tech", "summary": "安全摘要"}]})
    return TestClient(create_app(agent, sessions, hot_radar=radar))


def test_hot_radar_api_creates_subscription_and_scans(tmp_path):
    client = _client(tmp_path)

    created = client.post("/api/hot-radar/subscriptions", json={"keyword": "AI"})
    scanned = client.post("/api/hot-radar/scan")

    assert created.status_code == 201
    assert scanned.status_code == 200
    assert scanned.json()["new_count"] == 1
    assert client.get("/api/hot-radar/items").json()["items"][0]["title"] == "AI 新进展"


def test_hot_radar_api_rejects_blank_keyword(tmp_path):
    response = _client(tmp_path).post("/api/hot-radar/subscriptions", json={"keyword": " "})
    assert response.status_code == 422
