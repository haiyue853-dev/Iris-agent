from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.notifications.service import NotificationService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def _client(tmp_path) -> tuple[TestClient, NotificationService]:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(OpenAICompatibleProvider(object(), "test"), ToolRegistry(), 4), sessions, "test")
    notifications = NotificationService(tmp_path / "notifications")
    return TestClient(create_app(agent, sessions, notifications=notifications)), notifications


def test_notifications_api_lists_marks_read_and_deletes(tmp_path):
    client, notifications = _client(tmp_path)
    notification = notifications.create("radar scan", "one new item", "task-1", ("item-1",))

    assert client.get("/api/notifications").json()["notifications"][0]["read"] is False
    assert client.put(f"/api/notifications/{notification.id}/read").json()["read"] is True
    assert client.delete(f"/api/notifications/{notification.id}").status_code == 204
