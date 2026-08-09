"""Skill 中心服务：目录元数据 + 启用状态管理。"""

from dataclasses import dataclass, field
from pathlib import Path

from iris_agent.skill_center.catalog import SkillCatalog
from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.models import SkillDefinition, SkillInfo
from iris_agent.skill_center.repository import SkillStateRepository, now_iso


@dataclass(slots=True)
class SkillCenterService:
    """管理受信任的打包 Skill 元数据与启用状态；不执行任何 Skill 脚本。

    catalog_root: 包内 bundled 只读目录（SKILL.md 定义）
    settings_file: 用户数据目录中的状态文件（启用状态）
    """

    catalog_root: Path
    settings_file: Path
    _catalog: SkillCatalog = field(init=False, repr=False)
    _repository: SkillStateRepository = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._catalog = SkillCatalog(self.catalog_root)
        self._repository = SkillStateRepository(self.settings_file)

    def list_skills(self) -> list[SkillInfo]:
        states = self._repository.load()
        return [self._to_info(skill, states) for skill in self._catalog.list()]

    def get_skill(self, skill_id: str) -> SkillInfo:
        definition = self._lookup(skill_id)
        states = self._repository.load()
        return self._to_info(definition, states)

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillInfo:
        definition = self._lookup(skill_id)
        states = self._repository.load()
        states[definition.id] = {"enabled": bool(enabled), "updated_at": now_iso()}
        self._repository.save(states)
        return self._to_info(definition, states)

    def _lookup(self, skill_id: str) -> SkillDefinition:
        # 严格 ID 校验：只允许安全字符，任何路径片段直接视为未找到
        if not skill_id or any(ch in skill_id for ch in ("/", "\\", "..", " ")):
            raise SkillNotFoundError(f"未知 Skill: {skill_id}")
        definition = self._catalog.get(skill_id)
        if definition is None:
            raise SkillNotFoundError(f"未知 Skill: {skill_id}")
        return definition

    @staticmethod
    def _to_info(definition: SkillDefinition, states: dict) -> SkillInfo:
        state = states.get(definition.id, {})
        return SkillInfo(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            icon=definition.icon,
            category=definition.category,
            entry_view=definition.entry_view,
            version=definition.version,
            enabled=bool(state.get("enabled", True)),
        )
