"""Skill 中心服务：目录元数据、启用状态与用户技能读写。"""

import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from iris_agent.skill_center.catalog import SkillCatalog
from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.models import SUPPORTED_SKILL_TOOLSETS, SkillDefinition, SkillInfo
from iris_agent.skill_center.repository import SkillStateRepository, now_iso


@dataclass(slots=True)
class SkillCenterService:
    """管理内置 + 用户 Skill 的定义、启用状态与正文读写。

    catalog_root: 包内 bundled 只读目录（SKILL.md 定义）
    settings_file: 用户数据目录中的状态文件（启用状态）
    user_directory: 用户 Skill 可写目录（save_user_skill 写入）
    max_body_chars: 正文最大字符数
    """

    catalog_root: Path
    settings_file: Path
    user_directory: Path | None = None
    max_body_chars: int = 4000
    _catalog: SkillCatalog = field(init=False, repr=False)
    _user_catalog: SkillCatalog | None = field(init=False, repr=False)
    _repository: SkillStateRepository = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._catalog = SkillCatalog(self.catalog_root)
        if self.user_directory is not None:
            self.user_directory.mkdir(parents=True, exist_ok=True)
            self._user_catalog = SkillCatalog(self.user_directory, source="user")
        else:
            self._user_catalog = None
        self._repository = SkillStateRepository(self.settings_file)

    def _all_definitions(self) -> list[SkillDefinition]:
        merged = {skill.id: skill for skill in self._catalog.list()}
        if self._user_catalog is not None:
            for skill in self._user_catalog.list():
                merged[skill.id] = skill
        return list(merged.values())

    def list_skills(self) -> list[SkillInfo]:
        states = self._repository.load()
        return [self._to_info(skill, states) for skill in self._all_definitions()]

    def list_user_definitions(self) -> list[SkillDefinition]:
        """返回全部用户技能（含正文），供审查/去重使用。"""
        if self._user_catalog is None:
            return []
        return self._user_catalog.list()

    def get_skill(self, skill_id: str) -> SkillInfo:
        definition = self._lookup(skill_id)
        states = self._repository.load()
        return self._to_info(definition, states)

    def load_skill(self, skill_id: str) -> SkillDefinition:
        return self._lookup(skill_id)

    def load_user_skill(self, skill_id: str) -> SkillDefinition:
        """返回可编辑的用户 Skill 正文，拒绝内置 Skill。"""
        definition = self._lookup(skill_id)
        if definition.source != "user":
            raise ValueError("不能编辑内置 Skill")
        return definition

    def find_skill(self, id_or_name: str) -> SkillDefinition | None:
        """按 id 或名称查找技能，找不到返回 None。"""
        if not id_or_name or not id_or_name.strip():
            return None
        target = id_or_name.strip()
        for skill in self._all_definitions():
            if skill.id == target or skill.name == target:
                return skill
        return None

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillInfo:
        definition = self._lookup(skill_id)
        states = self._repository.load()
        states[definition.id] = {"enabled": bool(enabled), "updated_at": now_iso()}
        self._repository.save(states)
        return self._to_info(definition, states)

    def save_user_skill(self, name: str, description: str, content: str, allowed_toolsets: tuple[str, ...] = ()) -> SkillDefinition:
        if self.user_directory is None:
            raise ValueError("未配置用户技能目录")
        name = name.strip()
        if not name or not description.strip() or not content.strip():
            raise ValueError("技能名称、描述与内容不能为空")
        content = content[: self.max_body_chars]
        if any(item not in SUPPORTED_SKILL_TOOLSETS for item in allowed_toolsets) or len(set(allowed_toolsets)) != len(allowed_toolsets):
            raise ValueError("Skill 工具集不合法")

        existing = None
        for skill in self._user_catalog.list() if self._user_catalog else []:
            if skill.name == name:
                existing = skill
                break
        if existing is not None:
            skill_id = existing.id
            version = existing.version + 1
        else:
            skill_id = self._generate_id(name)
            version = 1

        self._write_skill(skill_id, name, description, version, content, allowed_toolsets)
        return self._lookup(skill_id)

    def delete_user_skill(self, skill_id: str) -> bool:
        """删除一个用户技能（仅限 user 目录），返回是否删除成功。"""
        if self.user_directory is None:
            return False
        definition = self.load_user_skill(skill_id)
        directory = self.user_directory / skill_id
        if not directory.is_dir():
            return False
        import shutil
        shutil.rmtree(directory)
        return True

    def _lookup(self, skill_id: str) -> SkillDefinition:
        if not skill_id or any(ch in skill_id for ch in ("/", "\\", "..", " ")):
            raise SkillNotFoundError(f"未知 Skill: {skill_id}")
        for skill in self._all_definitions():
            if skill.id == skill_id:
                return skill
        raise SkillNotFoundError(f"未知 Skill: {skill_id}")

    def _generate_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not slug:
            slug = "skill"
        return f"{slug}-{uuid.uuid4().hex[:6]}"

    def _write_skill(self, skill_id: str, name: str, description: str, version: int, content: str, allowed_toolsets: tuple[str, ...]) -> None:
        directory = self.user_directory / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        front = {
            "id": skill_id,
            "name": name,
            "description": description,
            "icon": "sparkles",
            "category": "custom",
            "entry_view": "chat",
            "version": version,
            "allowed_toolsets": list(allowed_toolsets),
        }
        front_text = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
        text = f"---\n{front_text}\n---\n{content}\n"
        path = directory / "SKILL.md"
        temporary_path: str | None = None
        try:
            fd, temporary_path = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

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
            source=definition.source,
            allowed_toolsets=definition.allowed_toolsets,
        )
