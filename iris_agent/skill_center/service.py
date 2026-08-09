"""Skill 中心服务：只管理受信任的、随 Iris 打包的 SKILL.md 元数据与启用状态，不执行任意脚本。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SkillCenterService:
    """Skill 中心服务（骨架）。任务 2 将补充目录扫描、schema 校验与状态持久化。"""

    root: Path
    settings_file: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
