from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
import tempfile
import threading
from typing import Any

from iris_agent.task_planning.models import TaskEvent, TaskPlan, TaskStep


class JsonTaskPlanRepository:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list(self, session_id: str | None = None) -> list[TaskPlan]:
        with self._lock:
            plans = [self._decode(item) for item in self._read()]
        if session_id:
            plans = [plan for plan in plans if plan.session_id == session_id]
        return sorted(plans, key=lambda plan: plan.updated_at, reverse=True)

    def get(self, plan_id: str) -> TaskPlan:
        for plan in self.list():
            if plan.id == plan_id:
                return plan
        raise KeyError(plan_id)

    def save(self, plan: TaskPlan) -> TaskPlan:
        with self._lock:
            items = self._read()
            encoded = asdict(plan)
            for index, item in enumerate(items):
                if item.get("id") == plan.id:
                    items[index] = encoded
                    break
            else:
                items.append(encoded)
            self._write(items)
        return plan

    def recover_interrupted(self) -> None:
        changed = False
        with self._lock:
            items = self._read()
            for item in items:
                if item.get("status") == "active":
                    for step in item.get("steps", []):
                        if step.get("status") == "running":
                            step["status"] = "pending"
                            changed = True
            if changed:
                self._write(items)

    def _read(self) -> list[dict[str, Any]]:
        path = self.directory / "task_plans.json"
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("task plan storage is unreadable") from exc
        if not isinstance(value, list):
            raise ValueError("task plan storage is invalid")
        return [item for item in value if isinstance(item, dict)]

    def _write(self, items: list[dict[str, Any]]) -> None:
        path = self.directory / "task_plans.json"
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
            raise ValueError("task plan storage cannot be saved") from exc

    @staticmethod
    def _decode(raw: dict[str, Any]) -> TaskPlan:
        steps = [
            TaskStep(**{**item, "events": [TaskEvent(**event) for event in item.get("events", []) if isinstance(event, dict)]})
            for item in raw.get("steps", []) if isinstance(item, dict)
        ]
        return TaskPlan(
            id=str(raw["id"]), session_id=str(raw["session_id"]), goal=str(raw["goal"]), steps=steps,
            skill_id=raw.get("skill_id"), status=str(raw.get("status", "active")),
            created_at=float(raw.get("created_at", 0)), updated_at=float(raw.get("updated_at", 0)),
        )
