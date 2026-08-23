"""SkillCatalog 解析与校验测试：打包 Skill 加载、非法定义拒绝。"""

from pathlib import Path

import pytest

from iris_agent.skill_center.catalog import SkillCatalog
from iris_agent.skill_center.errors import SkillValidationError

# 随包分发的 Skills 根目录
BUNDLED = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"


def _write_skill(root: Path, skill_id: str, body: str) -> Path:
    d = root / skill_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


_VALID = (
    "---\n"
    "id: demo-skill\n"
    "name: 演示技能\n"
    "description: 一个演示技能\n"
    "icon: spark\n"
    "category: productivity\n"
    "entry_view: chat\n"
    "version: 1\n"
    "---\n"
)


def test_loads_bundled_skills_without_document_workbench():
    catalog = SkillCatalog(BUNDLED)
    skills = catalog.list()
    ids = {s.id for s in skills}
    assert ids == {"daily-report", "uml", "hot-radar", "web-research"}
    for s in skills:
        assert s.name and s.description and s.entry_view and s.icon


def test_bundled_skill_has_expected_entry_views():
    catalog = SkillCatalog(BUNDLED)
    views = {s.id: s.entry_view for s in catalog.list()}
    assert views["daily-report"] == "reports"
    assert views["uml"] == "uml"
    assert views["hot-radar"] == "radar"


def test_catalog_discovers_and_reads_web_research_skill():
    skill = SkillCatalog(BUNDLED).get("web-research")

    assert skill is not None
    assert skill.name == "web-research"
    assert skill.description
    assert skill.icon and skill.category
    assert skill.entry_view == "chat"
    assert skill.version >= 1
    assert skill.source == "bundled"
    assert skill.body.strip()


def test_rejects_missing_required_field(tmp_path):
    body = _VALID.replace("description: 一个演示技能\n", "")
    _write_skill(tmp_path, "demo-skill", body)
    with pytest.raises(SkillValidationError):
        SkillCatalog(tmp_path).list()


def test_rejects_traversal_id(tmp_path):
    _write_skill(tmp_path, "demo-skill", _VALID.replace("id: demo-skill\n", "id: ../bad\n"))
    with pytest.raises(SkillValidationError):
        SkillCatalog(tmp_path).list()


def test_rejects_unknown_entry_view(tmp_path):
    _write_skill(tmp_path, "demo-skill", _VALID.replace("entry_view: chat\n", "entry_view: shell\n"))
    with pytest.raises(SkillValidationError):
        SkillCatalog(tmp_path).list()


def test_rejects_command_like_fields(tmp_path):
    _write_skill(tmp_path, "demo-skill", _VALID.replace("version: 1\n", "version: 1\nrun: echo pwned\n"))
    with pytest.raises(SkillValidationError):
        SkillCatalog(tmp_path).list()


def test_rejects_duplicate_ids(tmp_path):
    _write_skill(tmp_path, "a", _VALID.replace("id: demo-skill\n", "id: dup\n"))
    _write_skill(tmp_path, "b", _VALID.replace("id: demo-skill\n", "id: dup\n"))
    with pytest.raises(SkillValidationError):
        SkillCatalog(tmp_path).list()


def test_catalog_parses_body_and_source(tmp_path):
    _write_skill(tmp_path, "demo-skill", _VALID + "# Demo\n这是正文指令\n")
    skill = SkillCatalog(tmp_path).get("demo-skill")
    assert skill.body == "# Demo\n这是正文指令"
    assert skill.source == "bundled"


def test_web_research_defaults_to_a_bounded_quick_mode():
    skill = SkillCatalog(BUNDLED).get("web-research")

    assert "一次精准搜索" in skill.body
    assert "最多读取两个" in skill.body
    assert "明确要求深入研究" in skill.body
    assert "最多读取三个" in skill.body
