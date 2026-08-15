"""Atomic JSON persistence for the user profile."""

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

from iris_agent.profile.models import UserProfile


class ProfileLedgerError(RuntimeError):
    """The persisted user profile could not be safely read or written."""


class ProfileRepository:
    """Persists a single :class:`UserProfile` as a JSON document."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "profile.json"
        self.lock_path = root / "profile.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.RLock())

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def load(self) -> UserProfile:
        with self._lock:
            return self._load_unlocked()

    def save(self, profile: UserProfile) -> None:
        with self._lock:
            with self._cross_process_lock():
                self._save_unlocked(profile)

    def _load_unlocked(self) -> UserProfile:
        if not self.path.exists():
            return UserProfile()
        if not self.path.is_file():
            raise ProfileLedgerError("invalid user profile format")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise ProfileLedgerError("unable to read user profile") from exc
        except json.JSONDecodeError as exc:
            raise ProfileLedgerError("invalid user profile format") from exc
        try:
            return UserProfile.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise ProfileLedgerError("invalid user profile record") from exc

    def _save_unlocked(self, profile: UserProfile) -> None:
        if not isinstance(profile, UserProfile):
            raise ProfileLedgerError("invalid user profile record")
        payload = profile.to_dict()
        temporary_path: str | None = None
        try:
            fd, temporary_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, UnicodeError) as exc:
            raise ProfileLedgerError("unable to write user profile") from exc
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        import msvcrt

        try:
            self.lock_path.touch(exist_ok=True)
            handle = self.lock_path.open("r+b")
        except OSError as exc:
            raise ProfileLedgerError("unable to lock user profile") from exc

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
            raise ProfileLedgerError("unable to lock user profile") from exc

        try:
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    raise ProfileLedgerError("unable to lock user profile") from exc
        finally:
            try:
                handle.close()
            except OSError as exc:
                raise ProfileLedgerError("unable to lock user profile") from exc
