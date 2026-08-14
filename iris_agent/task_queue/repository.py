"""Atomic JSON persistence for the private task-queue ledger."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from iris_agent.task_queue.models import QueueJob


class QueueLedgerError(RuntimeError):
    """The persisted queue ledger could not be safely read or written."""


class QueueRepository:
    """Persists only the safe, FIFO serialisation of :class:`QueueJob`."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "queue.json"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.RLock())

    def load(self) -> list[QueueJob]:
        with self._lock:
            return self._load_unlocked()

    def save(self, jobs: list[QueueJob]) -> None:
        with self._lock:
            self._save_unlocked(jobs)

    def _load_unlocked(self) -> list[QueueJob]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise QueueLedgerError("unable to read queue ledger") from exc
        except json.JSONDecodeError as exc:
            raise QueueLedgerError("invalid queue ledger format") from exc

        if not isinstance(payload, dict) or set(payload) != {"jobs"}:
            raise QueueLedgerError("invalid queue ledger format")
        jobs = payload["jobs"]
        if not isinstance(jobs, list):
            raise QueueLedgerError("invalid queue ledger format")
        try:
            return [QueueJob.from_dict(item) for item in jobs]
        except (TypeError, ValueError) as exc:
            raise QueueLedgerError("invalid queue ledger record") from exc

    def _save_unlocked(self, jobs: list[QueueJob]) -> None:
        if not isinstance(jobs, list) or not all(isinstance(job, QueueJob) for job in jobs):
            raise QueueLedgerError("invalid queue ledger record")
        payload = {"jobs": [job.to_dict() for job in jobs]}
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
        """The process-local lock shared by repositories for this queue ledger."""
        return self._lock

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize a queue read-modify-write in and across Windows processes."""
        with self._lock:
            with self._cross_process_lock():
                yield

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        if os.name != "nt":
            yield
            return

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        normalized_path = os.path.normcase(str(self.path.resolve()))
        name = "Local\\iris-agent-queue-" + hashlib.sha256(normalized_path.encode("utf-8")).hexdigest()
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise QueueLedgerError("unable to create queue mutex")
        try:
            result = kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
            if result not in (0, 0x80):
                raise QueueLedgerError("unable to acquire queue mutex")
            try:
                yield
            finally:
                if not kernel32.ReleaseMutex(handle):
                    raise QueueLedgerError("unable to release queue mutex")
        finally:
            kernel32.CloseHandle(handle)
