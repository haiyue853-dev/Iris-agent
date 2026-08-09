"""文档服务（骨架）。任务 4/5 将补充存储、解析、草稿与导出。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DocumentService:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
