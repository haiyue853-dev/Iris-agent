"""Per-entry atomic JSON persistence for the knowledge base."""

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

from iris_agent.knowledge.models import KnowledgeEntry, _ID_PATTERN


class KnowledgeRepositoryError(RuntimeError):
    """The knowledge base could not be safely read or written."""


class KnowledgeRepository:
    """Persists one JSON file per knowledge entry under a root directory."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = root
        self.lock_path = root / ".lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.root.resolve(), threading.RLock())

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def list(self) -> list[KnowledgeEntry]:
        with self._lock:
            return self._list_unlocked()

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        with self._lock:
            return self._get_unlocked(entry_id)

    def save(self, entry: KnowledgeEntry) -> None:
        with self._lock:
            with self._cross_process_lock():
                self._save_unlocked(entry)

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            with self._cross_process_lock():
                return self._delete_unlocked(entry_id)

    def _safe_path(self, entry_id: str) -> Path:
        if not _ID_PATTERN.match(entry_id):
            raise KnowledgeRepositoryError("invalid knowledge id")
        return self.root / f"{entry_id}.json"

    def _list_unlocked(self) -> list[KnowledgeEntry]:
        entries: list[KnowledgeEntry] = []
        for path in sorted(self.root.glob("*.json")):
            entry = self._load_file(path)
            if entry is not None:
                entries.append(entry)
        return entries

    def _get_unlocked(self, entry_id: str) -> KnowledgeEntry | None:
        path = self._safe_path(entry_id)
        if not path.is_file():
            return None
        return self._load_file(path)

    def _save_unlocked(self, entry: KnowledgeEntry) -> None:
        path = self._safe_path(entry.id)
        temporary_path: str | None = None
        try:
            fd, temporary_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(entry.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as exc:
            raise KnowledgeRepositoryError("unable to write knowledge entry") from exc
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def _delete_unlocked(self, entry_id: str) -> bool:
        path = self._safe_path(entry_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError as exc:
            raise KnowledgeRepositoryError("unable to delete knowledge entry") from exc

    @staticmethod
    def _load_file(path: Path) -> KnowledgeEntry | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return KnowledgeEntry.from_dict(data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        import msvcrt

        try:
            self.lock_path.touch(exist_ok=True)
            handle = self.lock_path.open("r+b")
        except OSError as exc:
            raise KnowledgeRepositoryError("unable to lock knowledge base") from exc

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
            raise KnowledgeRepositoryError("unable to lock knowledge base") from exc

        try:
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    raise KnowledgeRepositoryError("unable to lock knowledge base") from exc
        finally:
            try:
                handle.close()
            except OSError as exc:
                raise KnowledgeRepositoryError("unable to lock knowledge base") from exc
