from pathlib import Path

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.registry import ToolRegistry


class PromptProvider:
    def __init__(self):
        self.messages = []

    def complete(self, messages, tools):
        self.messages = messages
        assert tools == []
        return ProviderResponse(content="优化后的提示词")


def test_prompt_optimizer_uses_bundled_skill_without_tools(tmp_path):
    provider = PromptProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    skills = SkillCenterService(
        Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled",
        tmp_path / "skills" / "settings.json",
    )
    client = TestClient(create_app(AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system"), sessions, skills=skills))

    response = client.post("/api/prompt/optimize", json={"prompt": "帮我写邮件"})

    assert response.status_code == 200
    assert response.json() == {"prompt": "优化后的提示词"}
    assert provider.messages[0].role == "system"
    assert "日常工作" in provider.messages[0].content
    assert provider.messages[1].content == "帮我写邮件"


def test_prompt_optimizer_rejects_blank_prompt(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    client = TestClient(create_app(AgentService(AgentLoop(PromptProvider(), ToolRegistry()), sessions, "system"), sessions))

    response = client.post("/api/prompt/optimize", json={"prompt": "   "})

    assert response.status_code == 422
