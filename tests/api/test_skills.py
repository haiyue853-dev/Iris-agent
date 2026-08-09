"""Skills API 测试：公开元数据、启停、坏 ID 4xx 且不泄露路径。"""

from pathlib import Path

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.registry import ToolRegistry

BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


def _client(tmp_path) -> TestClient:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    provider = OpenAICompatibleProvider(object(), "test-model")
    loop = AgentLoop(provider, ToolRegistry(), 4)
    agent = AgentService(loop, sessions, "test")
    skills = SkillCenterService(BUNDLED, tmp_path / "skills" / "settings.json")
    app = create_app(agent, sessions, skills=skills)
    return TestClient(app)


def test_list_skills_returns_public_metadata_only(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/skills")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["skills"], list)
    assert len(body["skills"]) == 4
    for item in body["skills"]:
        assert set(item.keys()) <= {"id", "name", "description", "icon", "category", "entry_view", "version", "enabled"}
        assert "path" not in item
        assert ".." not in str(item)


def test_get_single_skill(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/skills/uml")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "uml"
    assert body["entry_view"] == "uml"
    assert body["enabled"] is True


def test_toggle_enabled(tmp_path):
    client = _client(tmp_path)
    response = client.put("/api/skills/document-workbench/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert client.get("/api/skills/document-workbench").json()["enabled"] is False


def test_unknown_id_returns_4xx_without_path_leak(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/skills/does-not-exist")
    assert response.status_code == 404
    assert "C:" not in response.text and "D:" not in response.text and "\\" not in response.text

    traversal = client.get("/api/skills/..%2F..%2Fagent.yaml")
    assert traversal.status_code == 404 or traversal.status_code == 422


def test_invalid_enabled_payload_returns_422(tmp_path):
    client = _client(tmp_path)
    response = client.put("/api/skills/uml/enabled", json={"enabled": "yes"})
    assert response.status_code == 422
