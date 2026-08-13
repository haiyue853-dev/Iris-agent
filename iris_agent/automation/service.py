from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from iris_agent.hot_radar.service import HotRadarService


@dataclass(frozen=True, slots=True)
class AutomationTask:
    id: str
    name: str
    schedule: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AutomationExecution:
    id: str
    task_id: str
    trigger: str
    status: str
    summary: str = ""


class AutomationService:
    def __init__(self, root: Path, radar: HotRadarService):
        self.root, self.radar, self.path = root, radar, root / "automation.json"
        root.mkdir(parents=True, exist_ok=True)
        self._recover()

    def _read(self):
        if not self.path.exists(): return {"tasks": [], "executions": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def _recover(self):
        data = self._read(); changed = False
        for item in data["executions"]:
            if item["status"] == "running": item["status"] = "unknown"; changed = True
        if changed: self._write(data)

    @staticmethod
    def _valid_schedule(schedule: str) -> bool:
        return len(schedule.split()) == 5 and all(part.strip() for part in schedule.split())

    def create_task(self, name: str, schedule: str) -> AutomationTask:
        if not name.strip() or not self._valid_schedule(schedule): raise ValueError("任务名称或计划无效")
        task = AutomationTask(uuid4().hex, name.strip(), schedule.strip())
        data = self._read(); data["tasks"].append({"id": task.id, "name": task.name, "schedule": task.schedule, "enabled": task.enabled}); self._write(data)
        return task

    def list_tasks(self): return [AutomationTask(**item) for item in self._read()["tasks"]]
    def list_executions(self, task_id: str): return [AutomationExecution(**item) for item in reversed(self._read()["executions"]) if item["task_id"] == task_id]
    def _task(self, task_id): return next(item for item in self.list_tasks() if item.id == task_id)

    def set_enabled(self, task_id: str, enabled: bool) -> AutomationTask:
        data = self._read()
        for item in data["tasks"]:
            if item["id"] == task_id: item["enabled"] = bool(enabled); self._write(data); return AutomationTask(**item)
        raise KeyError(task_id)

    def claim(self, task_id: str, trigger: str) -> AutomationExecution:
        self._task(task_id); execution = AutomationExecution(uuid4().hex, task_id, trigger, "running")
        data = self._read(); data["executions"].append({"id": execution.id, "task_id": task_id, "trigger": trigger, "status": "running", "summary": ""}); self._write(data); return execution

    def run_now(self, task_id: str) -> AutomationExecution:
        execution = self.claim(task_id, "manual")
        try: result = self.radar.scan(); status, summary = "succeeded", result.summary
        except Exception: status, summary = "failed", "热点雷达扫描失败"
        data = self._read()
        for item in data["executions"]:
            if item["id"] == execution.id: item.update(status=status, summary=summary); self._write(data); return AutomationExecution(**item)
        raise RuntimeError("execution missing")
