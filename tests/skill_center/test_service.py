"""SkillCenterService 状态测试：默认启用、持久化、未知 ID。"""

from pathlib import Path

import pytest

from iris_agent.skill_center.catalog import SkillCatalog
from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.repository import SkillStateRepository
from iris_agent.skill_center.service import SkillCenterService

BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


def _build_service(tmp_path: Path) -> SkillCenterService:
    return SkillCenterService(BUNDLED, tmp_path / "settings.json")


def test_all_skills_enabled_by_default(tmp_path):
    service = _build_service(tmp_path)
    skills = service.list_skills()
    assert len(skills) == 3
    assert all(s.enabled for s in skills)


def test_toggle_persists_across_restart(tmp_path):
    service = _build_service(tmp_path)
    service.set_enabled("hot-radar", False)

    restarted = _build_service(tmp_path)
    state = {s.id: s.enabled for s in restarted.list_skills()}
    assert state["hot-radar"] is False
    assert state["uml"] is True


def test_unknown_id_raises_stable_error(tmp_path):
    service = _build_service(tmp_path)
    with pytest.raises(SkillNotFoundError):
        service.set_enabled("no-such-skill", True)
    with pytest.raises(SkillNotFoundError):
        service.get_skill("../../etc/passwd")
