"""Skill 启用状态仓储：JSON 原子持久化。"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class SkillStateRepository:
    """持久化每个 Skill 的启用状态到 settings.json（临时文件 + fsync + replace 原子写入）。"""

    def __init__(self, settings_file: Path):
        self.settings_file = settings_file

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.settings_file.is_file():
            return {}
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        skills = data.get("skills")
        if not isinstance(skills, dict):
            return {}
        return {str(k): v for k, v in skills.items() if isinstance(v, dict)}

    def save(self, states: dict[str, dict[str, Any]]) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"skills": states}
        fd, tmp_path = tempfile.mkstemp(dir=str(self.settings_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.settings_file)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
