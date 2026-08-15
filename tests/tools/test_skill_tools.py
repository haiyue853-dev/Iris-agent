from pathlib import Path

import pytest

from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.builtin.skill_tools import build_save_skill_tool, build_use_skill_tool

BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


@pytest.fixture
def service(tmp_path):
    return SkillCenterService(BUNDLED, tmp_path / "settings.json", user_directory=tmp_path / "skills")


def test_save_and_use_skill_tools(service):
    save = build_save_skill_tool(service)

    result = save.invoke({"name": "流程", "description": "d", "content": "步骤一"})

    assert result.ok
    skill_id = result.value["id"]

    use = build_use_skill_tool(service)
    loaded = use.invoke({"skill_id": skill_id})
    assert loaded.ok
    assert "步骤一" in loaded.value["content"]
    assert loaded.value["id"] == skill_id


def test_use_skill_loads_bundled_skill(service):
    use = build_use_skill_tool(service)

    result = use.invoke({"skill_id": "daily-report"})

    assert result.ok
    assert result.value["name"] == "AI 日报"


def test_use_skill_unknown_returns_error(service):
    use = build_use_skill_tool(service)

    result = use.invoke({"skill_id": "no-such-skill"})

    assert not result.ok
    assert result.error_code == "skill_not_found"
