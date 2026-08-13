from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime
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
        fields = schedule.split()
        ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
        return len(fields) == 5 and all(
            _valid_cron_field(field, minimum, maximum)
            for field, (minimum, maximum) in zip(fields, ranges)
        )

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

    def delete_task(self, task_id: str) -> None:
        data = self._read()
        remaining = [item for item in data["tasks"] if item["id"] != task_id]
        if len(remaining) == len(data["tasks"]):
            raise KeyError(task_id)
        data["tasks"] = remaining
        data["executions"] = [item for item in data["executions"] if item["task_id"] != task_id]
        self._write(data)

    def claim(self, task_id: str, trigger: str) -> AutomationExecution:
        self._task(task_id); execution = AutomationExecution(uuid4().hex, task_id, trigger, "running")
        data = self._read(); data["executions"].append({"id": execution.id, "task_id": task_id, "trigger": trigger, "status": "running", "summary": ""}); self._write(data); return execution

    def _run(self, task_id: str, trigger: str) -> AutomationExecution:
        execution = self.claim(task_id, trigger)
        try: result = self.radar.scan(); status, summary = "succeeded", result.summary
        except Exception: status, summary = "failed", "热点雷达扫描失败"
        data = self._read()
        for item in data["executions"]:
            if item["id"] == execution.id: item.update(status=status, summary=summary); self._write(data); return AutomationExecution(**item)
        raise RuntimeError("execution missing")

    def run_now(self, task_id: str) -> AutomationExecution:
        return self._run(task_id, "manual")

    def run_scheduled(self, task_id: str, window: str) -> AutomationExecution | None:
        trigger = f"schedule:{window}"
        if any(item.trigger == trigger for item in self.list_executions(task_id)):
            return None
        return self._run(task_id, trigger)


def _matches_cron_field(field: str, value: int, minimum: int, maximum: int) -> bool:
    for part in field.split(","):
        match = re.fullmatch(r"(\*|\d+)(?:/(\d+))?", part)
        if not match:
            return False
        base, step_text = match.groups()
        step = int(step_text) if step_text else 1
        if step < 1:
            return False
        if base == "*" and value % step == 0:
            return True
        if base != "*":
            start = int(base)
            if minimum <= start <= maximum and (
                value == start or (step_text is not None and value >= start and (value - start) % step == 0)
            ):
                return True
    return False


def _valid_cron_field(field: str, minimum: int, maximum: int) -> bool:
    for part in field.split(","):
        match = re.fullmatch(r"(\*|\d+)(?:/(\d+))?", part)
        if not match:
            return False
        base, step_text = match.groups()
        if step_text and int(step_text) < 1:
            return False
        if base != "*" and not minimum <= int(base) <= maximum:
            return False
    return True


def schedule_matches(schedule: str, now: datetime) -> bool:
    """Return whether a restricted five-field cron expression matches *now*."""
    fields = schedule.split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    return (
        _matches_cron_field(minute, now.minute, 0, 59)
        and _matches_cron_field(hour, now.hour, 0, 23)
        and _matches_cron_field(day, now.day, 1, 31)
        and _matches_cron_field(month, now.month, 1, 12)
        and _matches_cron_field(weekday, (now.weekday() + 1) % 7, 0, 6)
    )


class AutomationScheduler:
    """Small in-process scheduler for enabled automation tasks."""

    def __init__(self, automation: AutomationService):
        self.automation = automation
        self._last_window: set[tuple[str, str]] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_pending(self, now: datetime | None = None) -> int:
        moment = now or datetime.now()
        window = moment.strftime("%Y-%m-%dT%H:%M")
        ran = 0
        for task in self.automation.list_tasks():
            key = (task.id, window)
            if task.enabled and key not in self._last_window and schedule_matches(task.schedule, moment):
                execution = self.automation.run_scheduled(task.id, window)
                self._last_window.add(key)
                ran += int(execution is not None)
        self._last_window = {key for key in self._last_window if key[1] == window}
        return ran

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="iris-automation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            self._stop.wait(15)
