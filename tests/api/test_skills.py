"""Skills API 测试：公开元数据、启停、坏 ID 4xx 且不泄露路径。"""

from pathlib import Path

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.registry import ToolRegistry
from iris_agent.core.models import ProviderResponse

BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


def _client(tmp_path) -> TestClient:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    provider = OpenAICompatibleProvider(object(), "test-model")
    loop = AgentLoop(provider, ToolRegistry(), 4)
    agent = AgentService(loop, sessions, "test")
    skills = SkillCenterService(
        BUNDLED,
        tmp_path / "skills" / "settings.json",
        user_directory=tmp_path / "user-skills",
    )
    app = create_app(agent, sessions, skills=skills)
    return TestClient(app)


def test_list_skills_returns_public_metadata_only(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/skills")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["skills"], list)
    web_research = next(item for item in body["skills"] if item["id"] == "web-research")
    assert web_research["name"] == "web-research"
    assert web_research["description"]
    assert web_research["entry_view"] == "chat"
    assert web_research["enabled"] is True
    for item in body["skills"]:
        assert set(item.keys()) <= {"id", "name", "description", "icon", "category", "entry_view", "version", "enabled", "source", "allowed_toolsets"}
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
    response = client.put("/api/skills/hot-radar/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert client.get("/api/skills/hot-radar").json()["enabled"] is False


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


def test_user_skill_can_be_created_read_and_deleted(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/skills/user", json={
        "name": "会议整理",
        "description": "整理会议记录",
        "content": "把输入按结论、行动项整理。",
        "allowed_toolsets": ["safe", "research"],
    })
    assert created.status_code == 201
    skill_id = created.json()["id"]
    assert created.json()["source"] == "user"
    assert created.json()["allowed_toolsets"] == ["safe", "research"]

    loaded = client.get(f"/api/skills/{skill_id}/content")
    assert loaded.status_code == 200
    assert loaded.json()["content"] == "把输入按结论、行动项整理。"

    deleted = client.delete(f"/api/skills/user/{skill_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/skills/{skill_id}").status_code == 404


def test_user_skill_api_rejects_bundled_content_and_delete(tmp_path):
    client = _client(tmp_path)

    assert client.get("/api/skills/daily-report/content").status_code == 403
    assert client.delete("/api/skills/user/daily-report").status_code == 403


def test_chat_skill_is_hidden_from_user_message_and_injected_into_model_prompt(tmp_path):
    class CapturingProvider:
        model = "test-model"

        def __init__(self):
            self.messages = []

        def complete(self, messages, tools):
            self.messages = messages
            return ProviderResponse(content="完成")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    provider = CapturingProvider()
    skills = SkillCenterService(
        BUNDLED,
        tmp_path / "skills" / "settings.json",
        user_directory=tmp_path / "user-skills",
    )
    client = TestClient(create_app(
        AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system"),
        sessions,
        skills=skills,
    ))
    session_id = client.post("/api/sessions", json={"name": "会话"}).json()["id"]

    response = client.post("/api/chat/stream", json={
        "session_id": session_id,
        "message": "分析这个页面",
        "skill_id": "web-research",
    })

    assert response.status_code == 200
    user_message = next(message for message in provider.messages if message.role == "user")
    assert user_message.content == "分析这个页面"
    assert skills.load_skill("web-research").body in user_message.model_content
    history = client.get(f"/api/sessions/{session_id}").json()["messages"]
    assert next(message for message in history if message["role"] == "user")["content"] == "分析这个页面"
