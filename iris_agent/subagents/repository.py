from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
import tempfile
import threading
from typing import Any

from iris_agent.subagents.models import SubagentEvent, SubagentTask


class JsonSubagentRepository:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list(self, parent_session_id: str | None = None) -> list[SubagentTask]:
        with self._lock:
            tasks = [self._decode(item) for item in self._read()]
        if parent_session_id:
            tasks = [task for task in tasks if task.parent_session_id == parent_session_id]
        return sorted(tasks, key=lambda task: task.updated_at, reverse=True)

    def get(self, task_id: str) -> SubagentTask:
        for task in self.list():
            if task.id == task_id:
                return task
        raise KeyError(task_id)

    def save(self, task: SubagentTask) -> SubagentTask:
        with self._lock:
            items = self._read()
            encoded = asdict(task)
            for index, item in enumerate(items):
                if item.get("id") == task.id:
                    items[index] = encoded
                    break
            else:
                items.append(encoded)
            self._write(items)
        return task

    def recover_interrupted(self) -> None:
        changed = False
        with self._lock:
            items = self._read()
            for item in items:
                if item.get("status") == "running":
                    item["status"] = "queued"
                    changed = True
            if changed:
                self._write(items)

    def _read(self) -> list[dict[str, Any]]:
        path = self.directory / "subagents.json"
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("subagent storage is unreadable") from exc
        if not isinstance(value, list):
            raise ValueError("subagent storage is invalid")
        return [item for item in value if isinstance(item, dict)]

    def _write(self, items: list[dict[str, Any]]) -> None:
        path = self.directory / "subagents.json"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, delete=False, suffix=".tmp") as handle:
                temporary = Path(handle.name)
                json.dump(items, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if temporary:
                temporary.unlink(missing_ok=True)
            raise ValueError("subagent storage cannot be saved") from exc

    @staticmethod
    def _decode(raw: dict[str, Any]) -> SubagentTask:
        events = [SubagentEvent(**event) for event in raw.get("events", []) if isinstance(event, dict)]
        return SubagentTask(
            id=str(raw["id"]), parent_session_id=str(raw["parent_session_id"]), session_id=str(raw["session_id"]), parent_plan_id=raw.get("parent_plan_id"), parent_step_id=raw.get("parent_step_id"),
            title=str(raw["title"]), instruction=str(raw["instruction"]), allowed_tools=tuple(raw.get("allowed_tools", [])),
            max_tool_rounds=int(raw["max_tool_rounds"]), status=str(raw.get("status", "queued")),
            approval_call_id=raw.get("approval_call_id"), result=str(raw.get("result", "")), error=raw.get("error"), events=events,
            created_at=float(raw.get("created_at", 0)), updated_at=float(raw.get("updated_at", 0)),
        )
