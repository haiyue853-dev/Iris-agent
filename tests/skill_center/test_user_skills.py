"""用户 Skill 存储与目录合并测试。"""

from pathlib import Path

import pytest

from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.service import SkillCenterService

BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


def _build_service(tmp_path: Path) -> SkillCenterService:
    return SkillCenterService(
        BUNDLED,
        tmp_path / "settings.json",
        user_directory=tmp_path / "skills",
        max_body_chars=4000,
    )


def test_save_and_load_user_skill(tmp_path):
    service = _build_service(tmp_path)

    skill = service.save_user_skill("我的技能", "描述", "正文内容")

    assert skill.source == "user"
    assert service.load_skill(skill.id).body == "正文内容"


def test_load_user_skill_returns_editable_body(tmp_path):
    service = _build_service(tmp_path)
    created = service.save_user_skill("我的技能", "描述", "第一版")

    loaded = service.load_user_skill(created.id)

    assert loaded.id == created.id
    assert loaded.source == "user"
    assert loaded.body == "第一版"


def test_load_user_skill_rejects_bundled_skill(tmp_path):
    service = _build_service(tmp_path)

    with pytest.raises(ValueError, match="不能编辑内置 Skill"):
        service.load_user_skill("daily-report")


def test_save_updates_existing_skill_and_bumps_version(tmp_path):
    service = _build_service(tmp_path)

    first = service.save_user_skill("我的技能", "描述", "第一版")
    second = service.save_user_skill("我的技能", "描述", "第二版")

    assert first.id == second.id
    assert second.version == first.version + 1
    assert service.load_skill(second.id).body == "第二版"


def test_save_user_skill_persists_selected_toolsets(tmp_path):
    service = _build_service(tmp_path)

    saved = service.save_user_skill("联网整理", "整理搜索结果", "先搜索再整理", ("safe", "research"))

    assert saved.allowed_toolsets == ("safe", "research")
    assert service.get_skill(saved.id).allowed_toolsets == ("safe", "research")


def test_list_merges_bundled_and_user(tmp_path):
    service = _build_service(tmp_path)

    service.save_user_skill("自定义技能", "d", "c")

    ids = {s.id for s in service.list_skills()}
    assert "daily-report" in ids
    assert len(ids) == 5


def test_load_unknown_skill_raises(tmp_path):
    service = _build_service(tmp_path)

    with pytest.raises(SkillNotFoundError):
        service.load_skill("no-such-skill")


def test_save_rejects_blank_name(tmp_path):
    service = _build_service(tmp_path)

    with pytest.raises(ValueError):
        service.save_user_skill("", "d", "c")
