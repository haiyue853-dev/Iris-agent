"""Skill 目录：扫描随包分发的 SKILL.md，严格校验白名单字段，不执行任何内容。"""

import re
from pathlib import Path

import yaml

from iris_agent.skill_center.errors import SkillValidationError
from iris_agent.skill_center.models import SkillDefinition

# SKILL.md front matter 允许的字段白名单
_ALLOWED_FIELDS = {"id", "name", "description", "icon", "category", "entry_view", "version"}
_REQUIRED_FIELDS = {"id", "name", "description", "icon", "category", "entry_view", "version"}
# 允许跳转的视图（与前端视图保持一致）
_ALLOWED_ENTRY_VIEWS = {"chat", "aihot", "uml", "reports", "radar", "automation"}
_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillCatalog:
    """从固定根目录加载受信任的 Skill 定义（只读）。"""

    def __init__(self, root: Path):
        self.root = root

    def list(self) -> list[SkillDefinition]:
        if not self.root.is_dir():
            return []
        definitions: dict[str, SkillDefinition] = {}
        for entry in sorted(self.root.iterdir()):
            if not entry.is_dir():
                continue
            skill = self._load_skill_dir(entry)
            if skill.id in definitions:
                raise SkillValidationError(f"重复的 Skill id: {skill.id}")
            definitions[skill.id] = skill
        return list(definitions.values())

    def get(self, skill_id: str) -> SkillDefinition | None:
        for skill in self.list():
            if skill.id == skill_id:
                return skill
        return None

    def _load_skill_dir(self, directory: Path) -> SkillDefinition:
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            raise SkillValidationError(f"{directory.name} 缺少 SKILL.md")
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise SkillValidationError(f"无法读取 {directory.name}/SKILL.md: {exc}") from exc
        front = self._extract_front_matter(text, directory.name)
        return self._validate(front, directory.name)

    @staticmethod
    def _extract_front_matter(text: str, name: str) -> dict[str, object]:
        if not text.startswith("---"):
            raise SkillValidationError(f"{name}/SKILL.md 缺少 YAML front matter")
        end = text.find("\n---", 3)
        if end < 0:
            raise SkillValidationError(f"{name}/SKILL.md front matter 未闭合")
        try:
            parsed = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError as exc:
            raise SkillValidationError(f"{name}/SKILL.md front matter 解析失败: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SkillValidationError(f"{name}/SKILL.md front matter 必须是对象")
        return parsed

    def _validate(self, front: dict[str, object], name: str) -> SkillDefinition:
        # 只允许白名单字段；任何额外字段（含命令/脚本/路径类键名）一律拒绝
        for key in front:
            if key not in _ALLOWED_FIELDS:
                raise SkillValidationError(f"{name}/SKILL.md 含不允许的字段: {key}")
        missing = _REQUIRED_FIELDS - set(front)
        if missing:
            raise SkillValidationError(f"{name}/SKILL.md 缺少字段: {sorted(missing)}")

        skill_id = str(front["id"])
        if not _ID_PATTERN.fullmatch(skill_id) or ".." in skill_id or "/" in skill_id or "\\" in skill_id:
            raise SkillValidationError(f"{name}/SKILL.md 非法 id: {skill_id}")
        entry_view = str(front["entry_view"])
        if entry_view not in _ALLOWED_ENTRY_VIEWS:
            raise SkillValidationError(f"{name}/SKILL.md 未知 entry_view: {entry_view}")
        try:
            version = int(front["version"])
        except (TypeError, ValueError) as exc:
            raise SkillValidationError(f"{name}/SKILL.md version 必须是整数") from exc
        if version < 1:
            raise SkillValidationError(f"{name}/SKILL.md version 必须大于 0")

        return SkillDefinition(
            id=skill_id,
            name=str(front["name"]).strip(),
            description=str(front["description"]).strip(),
            icon=str(front["icon"]).strip(),
            category=str(front["category"]).strip(),
            entry_view=entry_view,
            version=version,
        )
