"""Atomic JSON persistence for the bounded task ledger."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from iris_agent.task_center.models import AgentTask


class TaskLedgerError(RuntimeError):
    """The persisted ledger could not be read safely and must not be replaced."""


class TaskLedgerRepository:
    """Persists only :class:`AgentTask`'s safe serialised representation."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "tasks.json"
        self.lock_path = root / "tasks.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.RLock())

    def load(self) -> list[AgentTask]:
        with self._lock:
            return self._load_unlocked()

    def save(self, tasks: list[AgentTask]) -> None:
        with self._lock:
            self._save_unlocked(tasks)

    def _load_unlocked(self) -> list[AgentTask]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise TaskLedgerError("无法读取任务账本") from exc
        except json.JSONDecodeError as exc:
            raise TaskLedgerError("任务账本格式无效") from exc
        if not isinstance(payload, dict):
            raise TaskLedgerError("任务账本格式无效")
        tasks = payload.get("tasks")
        if not isinstance(tasks, list):
            raise TaskLedgerError("任务账本格式无效")
        loaded: list[AgentTask] = []
        for item in tasks:
            if not isinstance(item, dict):
                raise TaskLedgerError("任务账本记录无效")
            try:
                loaded.append(AgentTask.from_dict(item))
            except (KeyError, TypeError, ValueError) as exc:
                raise TaskLedgerError("任务账本记录无效") from exc
        return loaded

    def _save_unlocked(self, tasks: list[AgentTask]) -> None:
        payload = {"tasks": [task.to_dict() for task in tasks]}
        fd, temporary_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    @property
    def lock(self) -> threading.RLock:
        """The process-local lock shared by repositories targeting this ledger."""
        return self._lock

    @contextmanager
    def transaction(self):
        """Serialize an entire ledger read-modify-write in and across processes."""
        with self._lock:
            with self._cross_process_lock():
                yield

    @contextmanager
    def _cross_process_lock(self):
        # The service currently targets Windows. A separate one-byte lock file keeps
        # the JSON replacement atomic while serialising the surrounding transaction.
        import msvcrt

        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("r+b") as handle:
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
