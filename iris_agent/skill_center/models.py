"""Skill 中心数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """受信任的打包 Skill 元数据（仅白名单字段，不含任何可执行内容）。"""

    id: str
    name: str
    description: str
    icon: str
    category: str
    entry_view: str
    version: int


@dataclass(frozen=True, slots=True)
class SkillInfo:
    """对外公开的 Skill 信息（元数据 + 启用状态）。"""

    id: str
    name: str
    description: str
    icon: str
    category: str
    entry_view: str
    version: int
    enabled: bool
