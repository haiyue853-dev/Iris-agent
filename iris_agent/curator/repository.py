"""Curator 报告仓储：每条报告一个 JSON 文件，原子写 + Windows 文件锁。"""

from __future__ import annotations

import errno
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from iris_agent.curator.models import CuratorReport

_ID_PATTERN = re.compile(r"^cur-[0-9a-f]{12}$")


class CuratorRepositoryError(RuntimeError):
    """The curator report store could not be safely read or written."""


class CuratorRepository:
    """Persists one JSON file per report under a root directory."""

    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, root: Path, max_reports: int = 50):
        self.root = root
        self.max_reports = max_reports
        self.lock_path = root / ".lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.root.resolve(), threading.RLock())

    def _safe_path(self, report_id: str) -> Path:
        if not _ID_PATTERN.match(report_id):
            raise CuratorRepositoryError("invalid curator report id")
        return self.root / f"{report_id}.json"

    def save(self, report: CuratorReport) -> None:
        with self._lock:
            with self._cross_process_lock():
                self._save_unlocked(report)
                self._trim_unlocked()

    def get(self, report_id: str) -> CuratorReport | None:
        with self._lock:
            path = self._safe_path(report_id)
            if not path.is_file():
                return None
            return self._load_file(path)

    def list(self) -> list[CuratorReport]:
        with self._lock:
            reports = [self._load_file(path) for path in sorted(self.root.glob("*.json"))]
            reports = [report for report in reports if report is not None]
            reports.sort(key=lambda item: item.created_at, reverse=True)
            return reports

    def _save_unlocked(self, report: CuratorReport) -> None:
        path = self._safe_path(report.id)
        temporary_path: str | None = None
        try:
            fd, temporary_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as exc:
            raise CuratorRepositoryError("unable to write curator report") from exc
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def _trim_unlocked(self) -> None:
        paths = sorted(self.root.glob("*.json"))
        if len(paths) <= self.max_reports:
            return
        for path in paths[: len(paths) - self.max_reports]:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _load_file(path: Path) -> CuratorReport | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CuratorReport.from_dict(data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        import msvcrt

        try:
            self.lock_path.touch(exist_ok=True)
            handle = self.lock_path.open("r+b")
        except OSError as exc:
            raise CuratorRepositoryError("unable to lock curator store") from exc

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
            raise CuratorRepositoryError("unable to lock curator store") from exc

        try:
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    raise CuratorRepositoryError("unable to lock curator store") from exc
        finally:
            try:
                handle.close()
            except OSError as exc:
                raise CuratorRepositoryError("unable to lock curator store") from exc
