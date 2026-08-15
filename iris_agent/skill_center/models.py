"""Skill 中心数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """受信任的 Skill 定义（白名单元数据 + 正文指令 + 来源）。"""

    id: str
    name: str
    description: str
    icon: str
    category: str
    entry_view: str
    version: int
    body: str = ""
    source: str = "bundled"


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
