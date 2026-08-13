from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(OpenAICompatibleProvider(object(), "test"), ToolRegistry(), 4), sessions, "test")
    radar = HotRadarService(tmp_path / "radar", sources={"tech": lambda: []})
    automation = AutomationService(tmp_path / "automation", radar)
    return TestClient(create_app(agent, sessions, automation=automation))


def test_automation_api_creates_toggles_and_runs_hot_radar_task(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/automation/tasks", json={"name": "雷达", "schedule": "0 * * * *"})
    task_id = created.json()["id"]

    assert created.status_code == 201
    assert client.put(f"/api/automation/tasks/{task_id}/enabled", json={"enabled": False}).json()["enabled"] is False
    assert client.post(f"/api/automation/tasks/{task_id}/run").json()["status"] == "succeeded"
    assert client.get(f"/api/automation/tasks/{task_id}/executions").json()["executions"][0]["trigger"] == "manual"


def test_automation_api_rejects_invalid_schedule(tmp_path):
    assert _client(tmp_path).post("/api/automation/tasks", json={"name": "雷达", "schedule": "daily"}).status_code == 422
