"""Lifecycle and safe event mapping for persistent Agent tasks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

from iris_agent.task_center.models import AgentTask, TaskEvent
from iris_agent.task_center.repository import TaskLedgerRepository


MAX_TASKS = 100
MAX_EVENTS = 100
TERMINAL_STATUSES = frozenset({"completed", "failed", "stopped"})
_SAFE_TOOL_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,120}\Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskCenterService:
    """Stores a bounded, payload-free timeline for each Agent request."""

    def __init__(self, root: Path, *, recover_unfinished: bool = True):
        self.repository = TaskLedgerRepository(root)
        self._approval_states: dict[tuple[str, str], tuple[str, str]] = {}
        if recover_unfinished:
            self._recover_unfinished()

    def create_task(self, session_id: str, user_message: str) -> AgentTask:
        with self.repository.transaction():
            timestamp = _now()
            task = AgentTask(
                id=f"task_{uuid4().hex}",
                session_id=session_id,
                request_summary=user_message.strip()[:120],
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                events=(self._event("request_submitted", "已提交请求", timestamp=timestamp),),
            )
            tasks = self.repository.load()
            tasks.append(task)
            self._save_bounded(tasks)
            return task

    def create_queued_task(self, session_id: str, user_message: str) -> AgentTask:
        with self.repository.transaction():
            timestamp = _now()
            task = AgentTask(
                id=f"task_{uuid4().hex}",
                session_id=session_id,
                request_summary=user_message.strip()[:120],
                status="queued",
                created_at=timestamp,
                updated_at=timestamp,
                events=(self._event("request_queued", "已加入队列", timestamp=timestamp),),
            )
            tasks = self.repository.load()
            tasks.append(task)
            self._save_bounded(tasks)
            return task

    def get_task(self, task_id: str) -> AgentTask | None:
        return next((task for task in self.repository.load() if task.id == task_id), None)

    def list_tasks(self, limit: int = 50, session_id: str | None = None) -> list[AgentTask]:
        bounded_limit = max(0, min(int(limit), MAX_TASKS))
        tasks = self.repository.load()
        if session_id is not None:
            tasks = [task for task in tasks if task.session_id == session_id]
        ordered = sorted(tasks, key=lambda task: task.updated_at, reverse=True)
        return [task.without_events() for task in ordered[:bounded_limit]]

    def tool_started(self, task_id: str, tool_name: str, **_ignored: object) -> AgentTask:
        tool_name = self._safe_tool_name(tool_name)
        return self._append(task_id, "tool_started", f"开始调用工具：{tool_name}", tool_name=tool_name)

    def approval_requested(self, task_id: str, call_id: str, tool_name: str, **_ignored: object) -> AgentTask:
        tool_name = self._safe_tool_name(tool_name)
        task = self._append(
            task_id,
            "approval_requested",
            f"等待工具审批：{tool_name}",
            tool_name=tool_name,
            status="awaiting_approval",
        )
        self._approval_states[(task_id, call_id)] = ("awaiting", tool_name)
        return task

    def record_approval(self, task_id: str, call_id: str, tool_name: str, approved: bool, **_ignored: object) -> AgentTask:
        tool_name = self._safe_tool_name(tool_name)
        state = self._approval_states.get((task_id, call_id))
        if state is None or state[0] != "awaiting" or state[1] != tool_name:
            raise ValueError("审批调用 ID 无效")
        outcome = "approval_approved" if approved else "approval_rejected"
        label = f"已{'批准' if approved else '拒绝'}工具调用：{tool_name}"
        task = self._append(task_id, outcome, label, tool_name=tool_name, status="running")
        self._approval_states[(task_id, call_id)] = ("approved" if approved else "rejected", tool_name)
        return task

    def tool_finished(
        self,
        task_id: str,
        tool_name: str,
        duration_ms: int | None = None,
        *,
        call_id: str | None = None,
        succeeded: bool = True,
        **_ignored: object,
    ) -> AgentTask:
        tool_name = self._safe_tool_name(tool_name)
        with self.repository.transaction():
            if call_id is not None:
                state = self._approval_states.get((task_id, call_id))
                if state is None:
                    raise ValueError("工具调用 ID 无效")
                outcome, approved_tool_name = state
                if approved_tool_name != tool_name:
                    raise ValueError("工具调用 ID 与工具不匹配")
                if outcome == "rejected" and succeeded:
                    raise ValueError("工具调用已被拒绝")
                if outcome == "completed":
                    raise ValueError("工具调用已完成")
                if outcome not in {"approved", "rejected"}:
                    raise ValueError("工具调用尚未获批")
            elif any(
                pending_task_id == task_id and pending_tool_name == tool_name
                for (pending_task_id, _), (_, pending_tool_name) in self._approval_states.items()
            ):
                raise ValueError("审批工具结束需要调用 ID")
            task = self._append_locked(
                task_id,
                "tool_succeeded" if succeeded else "tool_failed",
                f"工具调用{'成功' if succeeded else '失败'}：{tool_name}",
                tool_name=tool_name,
                duration_ms=duration_ms,
                status="running",
            )
            if call_id is not None:
                self._approval_states[(task_id, call_id)] = ("completed", tool_name)
            return task

    def touch(self, task_id: str, **_ignored: object) -> AgentTask:
        """Record progress without persisting response text or adding a timeline event."""
        with self.repository.transaction():
            tasks = self.repository.load()
            for index, task in enumerate(tasks):
                if task.id != task_id:
                    continue
                if task.status in TERMINAL_STATUSES:
                    return task
                updated = replace(task, updated_at=_now())
                tasks[index] = updated
                self._save_bounded(tasks)
                return updated
            raise KeyError(task_id)

    def start(self, task_id: str) -> AgentTask:
        return self._append(task_id, "execution_started", "开始执行", status="running")

    def request_stop(self, task_id: str) -> AgentTask:
        return self._append(task_id, "stop_requested", "已请求停止")

    def complete(self, task_id: str, **_ignored: object) -> AgentTask:
        return self._append(task_id, "reply_completed", "已生成回复", status="completed", terminal=True)

    def fail(self, task_id: str, **_ignored: object) -> AgentTask:
        return self._append(task_id, "execution_failed", "任务执行失败", status="failed", terminal=True)

    def stop(self, task_id: str) -> AgentTask:
        return self._append(task_id, "execution_interrupted", "执行已中断", status="stopped", terminal=True)

    def _recover_unfinished(self) -> None:
        with self.repository.transaction():
            tasks = self.repository.load()
            recovered = False
            for index, task in enumerate(tasks):
                if task.status not in {"running", "awaiting_approval"}:
                    continue
                timestamp = _now()
                tasks[index] = replace(
                    task,
                    status="stopped",
                    updated_at=timestamp,
                    finished_at=timestamp,
                    events=(
                        *task.events,
                        self._event("execution_interrupted", "服务重启，执行未完成", timestamp=timestamp),
                    )[-MAX_EVENTS:],
                )
                recovered = True
            if recovered:
                self._save_bounded(tasks)

    def _append(
        self,
        task_id: str,
        event_type: str,
        label: str,
        *,
        tool_name: str | None = None,
        duration_ms: int | None = None,
        status: str | None = None,
        terminal: bool = False,
    ) -> AgentTask:
        with self.repository.transaction():
            return self._append_locked(task_id, event_type, label, tool_name, duration_ms, status, terminal)

    def _append_locked(
        self,
        task_id: str,
        event_type: str,
        label: str,
        tool_name: str | None = None,
        duration_ms: int | None = None,
        status: str | None = None,
        terminal: bool = False,
    ) -> AgentTask:
        tasks = self.repository.load()
        for index, task in enumerate(tasks):
            if task.id != task_id:
                continue
            if task.status in TERMINAL_STATUSES:
                return task
            self._validate_transition(task.status, event_type)
            timestamp = _now()
            next_status = status or task.status
            updated = replace(
                task,
                status=next_status,
                updated_at=timestamp,
                finished_at=timestamp if terminal else task.finished_at,
                events=(
                    *task.events,
                    self._event(event_type, label, tool_name, duration_ms, timestamp),
                )[-MAX_EVENTS:],
            )
            tasks[index] = updated
            self._save_bounded(tasks)
            return updated
        raise KeyError(task_id)

    @staticmethod
    def _validate_transition(current_status: str, event_type: str) -> None:
        if current_status == "queued" and event_type not in {
            "execution_started",
            "stop_requested",
            "reply_completed",
            "execution_failed",
            "execution_interrupted",
        }:
            raise ValueError("任务正在队列中，不能继续执行")
        if event_type == "execution_started" and current_status != "queued":
            raise ValueError("任务不在队列中，不能开始执行")
        if current_status == "awaiting_approval" and event_type not in {
            "approval_approved",
            "approval_rejected",
            "stop_requested",
            "execution_failed",
            "execution_interrupted",
        }:
            raise ValueError("任务正在等待审批，不能继续执行")

    @staticmethod
    def _event(
        event_type: str,
        label: str,
        tool_name: str | None = None,
        duration_ms: int | None = None,
        timestamp: str | None = None,
    ) -> TaskEvent:
        return TaskEvent(
            id=f"event_{uuid4().hex}",
            type=event_type,
            label=label,
            created_at=timestamp or _now(),
            tool_name=tool_name,
            duration_ms=max(0, int(duration_ms)) if duration_ms is not None else None,
        )

    @staticmethod
    def _safe_tool_name(tool_name: object) -> str:
        candidate = str(tool_name)
        return candidate if _SAFE_TOOL_NAME.fullmatch(candidate) else "unknown_tool"

    def _save_bounded(self, tasks: list[AgentTask]) -> None:
        bounded = sorted(tasks, key=lambda task: task.updated_at, reverse=True)[:MAX_TASKS]
        self.repository.save(bounded)
