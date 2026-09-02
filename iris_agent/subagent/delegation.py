from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from iris_agent.subagent.models import SubagentRequest, SubagentResult, WorkflowResult, WorkflowStep
from iris_agent.core.models import Message
from iris_agent.sessions.base import SessionRepository


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "interrupted"})
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DelegationRecord:
    id: str
    parent_task_id: str | None
    session_id: str | None
    status: str
    goal: str
    context: str | None
    allowed_tools: tuple[str, ...] | None
    max_rounds: int | None
    result: str
    error: str | None
    side_effect_started: bool
    created_at: float
    updated_at: float


class DelegationRepository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS delegations (id TEXT PRIMARY KEY, parent_task_id TEXT, status TEXT NOT NULL, goal TEXT NOT NULL, context TEXT, allowed_tools TEXT, max_rounds INTEGER, result TEXT NOT NULL DEFAULT '', error TEXT, side_effect_started INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(delegations)")}
            if "session_id" not in columns:
                connection.execute("ALTER TABLE delegations ADD COLUMN session_id TEXT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def create(self, request: SubagentRequest, parent_task_id: str | None = None, session_id: str | None = None) -> DelegationRecord:
        now = time.time()
        record = DelegationRecord(f"delegation_{uuid.uuid4().hex}", parent_task_id, session_id, "queued", request.goal, request.context, None if request.allowed_tools is None else tuple(request.allowed_tools), request.max_rounds, "", None, False, now, now)
        with self._lock, self._connect() as connection:
            connection.execute("INSERT INTO delegations (id, parent_task_id, session_id, status, goal, context, allowed_tools, max_rounds, result, error, side_effect_started, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (record.id, record.parent_task_id, record.session_id, record.status, record.goal, record.context, None if record.allowed_tools is None else json.dumps(record.allowed_tools, ensure_ascii=False), record.max_rounds, record.result, record.error, 0, now, now))
        return record

    def get(self, delegation_id: str) -> DelegationRecord:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM delegations WHERE id = ?", (delegation_id,)).fetchone()
        if row is None:
            raise KeyError(delegation_id)
        allowed = None if row["allowed_tools"] is None else tuple(json.loads(row["allowed_tools"]))
        return DelegationRecord(row["id"], row["parent_task_id"], row["session_id"], row["status"], row["goal"], row["context"], allowed, row["max_rounds"], row["result"], row["error"], bool(row["side_effect_started"]), row["created_at"], row["updated_at"])

    def list(self, limit: int = 50, parent_task_id: str | None = None) -> list[DelegationRecord]:
        safe_limit = max(1, min(limit, 200))
        query = "SELECT id FROM delegations"
        values: list[object] = []
        if parent_task_id is not None:
            query += " WHERE parent_task_id = ?"
            values.append(parent_task_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(safe_limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self.get(row["id"]) for row in rows]

    def _set(self, delegation_id: str, status: str, *, result: str | None = None, error: str | None = None) -> None:
        assignments = ["status = ?", "updated_at = ?"]
        values: list[object] = [status, time.time()]
        if result is not None:
            assignments.append("result = ?")
            values.append(result)
        if error is not None:
            assignments.append("error = ?")
            values.append(error)
        values.append(delegation_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(f"UPDATE delegations SET {', '.join(assignments)} WHERE id = ?", values)
            if cursor.rowcount != 1:
                raise KeyError(delegation_id)

    def mark_running(self, delegation_id: str) -> None:
        self._set(delegation_id, "running")

    def finish(self, delegation_id: str, result: SubagentResult) -> None:
        self._set(delegation_id, "succeeded" if result.ok else "failed", result=result.result)

    def cancel(self, delegation_id: str) -> bool:
        record = self.get(delegation_id)
        if record.status in TERMINAL_STATUSES:
            return False
        self._set(delegation_id, "cancelled", error="cancelled")
        return True

    def recover(self) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("UPDATE delegations SET status = 'interrupted', error = 'process_restarted', updated_at = ? WHERE status IN ('running', 'awaiting_approval', 'cancel_requested')", (time.time(),))
            return cursor.rowcount


class DelegationService:
    def __init__(self, runner, repository: DelegationRepository, max_workers: int = 3, sessions: SessionRepository | None = None):
        self.runner = runner
        self.repository = repository
        self.sessions = sessions
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._max_workers = max(1, max_workers)
        self._pool = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="iris-delegation")
        self.repository.recover()


    def run_parallel(self, requests: list[SubagentRequest], max_workers: int | None = None) -> list[SubagentResult]:
        if not requests:
            return []
        workers = max(1, min(max_workers or self._max_workers, len(requests)))
        results: list[SubagentResult] = [SubagentResult(False, "", 0)] * len(requests)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="iris-delegation-batch") as pool:
            futures = {pool.submit(self.run, request): index for index, request in enumerate(requests)}
            for future, index in futures.items():
                results[index] = future.result()
        return results

    def run_workflow(self, steps: list[WorkflowStep]) -> WorkflowResult:
        indexed = {step.id: step for step in steps}
        if not indexed or len(indexed) != len(steps) or any(not step.id or not step.goal or any(dep not in indexed or dep == step.id for dep in step.depends_on) for step in steps):
            raise ValueError("workflow steps are invalid")
        pending = set(indexed)
        results: dict[str, SubagentResult] = {}
        while pending:
            ready = [indexed[item] for item in pending if all(dep in results for dep in indexed[item].depends_on)]
            if not ready:
                raise ValueError("workflow dependencies contain a cycle")
            requests = []
            for step in ready:
                inherited = "\n\n".join(f"[{dep} 的结论]\n{results[dep].result}" for dep in step.depends_on)
                context = "\n\n".join(item for item in (step.context, inherited) if item)
                requests.append(SubagentRequest(step.goal, context or None, step.allowed_tools, step.max_rounds))
            for step, result in zip(ready, self.run_parallel(requests), strict=True):
                results[step.id] = result
                pending.remove(step.id)
        return WorkflowResult(results)
    def run(self, request: SubagentRequest, parent_task_id: str | None = None, delegation_id: str | None = None, publish_to_session: bool = False) -> SubagentResult:
        record = self.repository.create(request, parent_task_id) if delegation_id is None else self.repository.get(delegation_id)
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[record.id] = cancel_event
        self.repository.mark_running(record.id)
        try:
            result = self.runner.run(request, is_cancelled=cancel_event.is_set)
            if cancel_event.is_set():
                self.repository.cancel(record.id)
                return SubagentResult(False, result.result, result.rounds, record.id)
            self.repository.finish(record.id, result)
            if publish_to_session:
                self._publish_to_session(record, result)
            return SubagentResult(result.ok, result.result, result.rounds, record.id)
        except Exception as exc:
            self.repository._set(record.id, "failed", error=str(exc))
            if publish_to_session:
                self._publish_to_session(record, SubagentResult(False, "", 0), str(exc))
            return SubagentResult(False, "", 0, record.id)
        finally:
            with self._lock:
                self._cancel_events.pop(record.id, None)

    def submit_background(self, request: SubagentRequest, parent_task_id: str | None = None, session_id: str | None = None) -> str:
        record = self.repository.create(request, parent_task_id, session_id)
        self._pool.submit(self.run, request, parent_task_id, record.id, True)
        return record.id

    def _publish_to_session(self, record: DelegationRecord, result: SubagentResult, error: str | None = None) -> None:
        if self.sessions is None or not record.session_id:
            return
        if result.ok:
            content = f"子代理任务已完成：{record.goal}\n\n{result.result}"
        else:
            content = f"子代理任务失败：{record.goal}\n\n{error or result.result or '未返回错误详情'}"
        try:
            self.sessions.append(record.session_id, Message(role="assistant", content=content))
        except Exception:
            logger.warning("后台委派完成，但无法回填原会话：%s", record.session_id, exc_info=True)

    def cancel(self, delegation_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(delegation_id)
            if event is not None:
                event.set()
        return self.repository.cancel(delegation_id)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
