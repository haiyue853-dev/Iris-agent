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
    return TestClient(create_app(agent, sessions, hot_radar=HotRadarService(tmp_path / "radar", sources={})))


def test_hot_radar_api_deletes_subscription(tmp_path):
    client = _client(tmp_path)
    subscription_id = client.post("/api/hot-radar/subscriptions", json={"keyword": "AI"}).json()["id"]

    assert client.delete(f"/api/hot-radar/subscriptions/{subscription_id}").status_code == 204
    assert client.get("/api/hot-radar/subscriptions").json()["subscriptions"] == []
