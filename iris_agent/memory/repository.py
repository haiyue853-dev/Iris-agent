"""Atomic JSON persistence for the memory ledger."""

from __future__ import annotations

import errno
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from iris_agent.memory.models import MemoryEntry


class MemoryLedgerError(RuntimeError):
    """The persisted memory ledger could not be safely read or written."""


class MemoryRepository:
    """Persists only the safe, whitelisted serialisation of :class:`MemoryEntry`."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "memory.json"
        self.lock_path = root / "memory.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.RLock())

    @property
    def lock(self) -> threading.RLock:
        """The process-local lock shared by repositories for this memory ledger."""
        return self._lock

    def load(self) -> list[MemoryEntry]:
        with self._lock:
            return self._load_unlocked()

    def save(self, entries: list[MemoryEntry]) -> None:
        with self._lock:
            with self._cross_process_lock():
                self._save_unlocked(entries)

    def _load_unlocked(self) -> list[MemoryEntry]:
        if not self.path.exists():
            return []
        if not self.path.is_file():
            raise MemoryLedgerError("invalid memory ledger format")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise MemoryLedgerError("unable to read memory ledger") from exc
        except json.JSONDecodeError as exc:
            raise MemoryLedgerError("invalid memory ledger format") from exc

        if not isinstance(payload, dict) or set(payload) != {"entries"}:
            raise MemoryLedgerError("invalid memory ledger format")
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise MemoryLedgerError("invalid memory ledger format")
        try:
            return [MemoryEntry.from_dict(item) for item in entries]
        except (TypeError, ValueError) as exc:
            raise MemoryLedgerError("invalid memory ledger record") from exc

    def _save_unlocked(self, entries: list[MemoryEntry]) -> None:
        if not isinstance(entries, list) or not all(isinstance(item, MemoryEntry) for item in entries):
            raise MemoryLedgerError("invalid memory ledger record")
        payload = {"entries": [item.to_dict() for item in entries]}
        temporary_path: str | None = None
        try:
            fd, temporary_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, UnicodeError) as exc:
            raise MemoryLedgerError("unable to write memory ledger") from exc
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        # The service currently targets Windows. This empty sidecar only
        # supplies a one-byte OS lock; memory records remain in memory.json.
        import msvcrt

        try:
            self.lock_path.touch(exist_ok=True)
            handle = self.lock_path.open("r+b")
        except OSError as exc:
            raise MemoryLedgerError("unable to lock memory ledger") from exc

        try:
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno != errno.EACCES and getattr(exc, "winerror", None) != 33:
                        raise
                    time.sleep(0.01)
        except OSError as exc:
            raise MemoryLedgerError("unable to lock memory ledger") from exc

        try:
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    raise MemoryLedgerError("unable to lock memory ledger") from exc
        finally:
            try:
                handle.close()
            except OSError as exc:
                raise MemoryLedgerError("unable to lock memory ledger") from exc
