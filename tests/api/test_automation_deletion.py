from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def _client(tmp_path) -> TestClient:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(OpenAICompatibleProvider(object(), "test"), ToolRegistry(), 4), sessions, "test")
    automation = AutomationService(tmp_path / "automation", HotRadarService(tmp_path / "radar", sources={}))
    return TestClient(create_app(agent, sessions, automation=automation))


def test_automation_api_deletes_task(tmp_path):
    client = _client(tmp_path)
    task_id = client.post("/api/automation/tasks", json={"name": "radar", "schedule": "0 * * * *"}).json()["id"]

    assert client.delete(f"/api/automation/tasks/{task_id}").status_code == 204
    assert client.get("/api/automation/tasks").json()["tasks"] == []
