"""热点雷达服务（骨架）。任务 7/8 将补充订阅、摘要与调度。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class HotRadarService:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
