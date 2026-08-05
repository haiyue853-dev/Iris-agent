from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
from typing import ContextManager, Protocol

from iris_agent.reports.errors import (
    ReportNotFoundError,
    ReportStorageError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.models import DailyReport, ReportSections, ReportSourceMessage, ReportVersion

logger = logging.getLogger(__name__)


class DailyReportRepository(Protocol):
    def list(self) -> list[DailyReport]: ...
    def get(self, report_date: str) -> DailyReport: ...
    def save(self, report: DailyReport, expected_version: int | None = None) -> None: ...
    def report_lock(self, report_date: str) -> ContextManager[None]: ...


class JsonDailyReportRepository:
    def __init__(self, directory: str | Path, max_versions: int = 20):
        if max_versions < 1:
            raise ReportValidationError("日报版本上限必须大于 0")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._root = self.directory.resolve()
        self.max_versions = max_versions
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, report_date: str) -> threading.RLock:
        self._validate_date(report_date)
        with self._locks_guard:
            return self._locks.setdefault(report_date, threading.RLock())

    @contextmanager
    def report_lock(self, report_date: str) -> Iterator[None]:
        with self._lock_for(report_date):
            yield

    @staticmethod
    def _validate_date(report_date: str) -> None:
        try:
            parsed = date.fromisoformat(report_date)
        except (TypeError, ValueError) as exc:
            raise ReportValidationError("日报日期必须使用 YYYY-MM-DD 格式", code="report_invalid_date") from exc
        if parsed.isoformat() != report_date:
            raise ReportValidationError("日报日期必须使用 YYYY-MM-DD 格式", code="report_invalid_date")

    def _path(self, report_date: str) -> Path:
        self._validate_date(report_date)
        target = (self.directory / f"{report_date}.json").resolve()
        if target.parent != self._root:
            raise ReportValidationError("日报日期无效", code="report_invalid_date")
        return target

    def list(self) -> list[DailyReport]:
        reports: list[DailyReport] = []
        for path in self.directory.glob("????-??-??.json"):
            reports.append(self.get(path.stem))
        return sorted(reports, key=lambda item: item.updated_at, reverse=True)

    def get(self, report_date: str) -> DailyReport:
        with self._lock_for(report_date):
            path = self._path(report_date)
            if not path.exists():
                raise ReportNotFoundError("日报不存在")
            return self._read(path)

    def save(self, report: DailyReport, expected_version: int | None = None) -> None:
        with self._lock_for(report.date):
            path = self._path(report.date)
            if path.exists():
                current = self._read(path)
                if expected_version is None or current.current_version != expected_version:
                    raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")
            elif expected_version not in {None, 0}:
                raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")

            candidate = self._trimmed_copy(report)
            try:
                payload = json.dumps(self._encode(candidate), ensure_ascii=False, indent=2, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ReportStorageError("无法序列化日报") from exc

            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.directory,
                    delete=False,
                    suffix=".tmp",
                ) as handle:
                    temp_path = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
            except OSError as exc:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("无法清理日报临时文件", exc_info=True)
                raise ReportStorageError("无法保存日报") from exc

    def _read(self, path: Path) -> DailyReport:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root must be an object")
            return self._decode(raw)
        except ReportValidationError as exc:
            raise ReportStorageError("日报文件内容损坏") from exc
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReportStorageError("无法读取日报文件") from exc

    def _trimmed_copy(self, report: DailyReport) -> DailyReport:
        versions = list(report.versions)
        if len(versions) > self.max_versions:
            versions = versions[-self.max_versions :]
            if report.current_version not in {item.number for item in versions}:
                current = report.current
                versions[0] = current
                versions.sort(key=lambda item: item.number)
        return DailyReport.create(
            report.date,
            report.source_notes,
            report.source_session_id,
            report.source_chat_snapshot,
            versions,
            report.current_version,
            report.created_at,
            report.updated_at,
        )

    @staticmethod
    def _encode(report: DailyReport) -> dict[str, object]:
        return {
            "date": report.date,
            "source_notes": report.source_notes,
            "source_session_id": report.source_session_id,
            "source_chat_snapshot": [
                {"role": item.role, "content": item.content} for item in report.source_chat_snapshot
            ],
            "versions": [
                {
                    "number": item.number,
                    "sections": item.sections.to_dict(),
                    "kind": item.kind,
                    "instruction": item.instruction,
                    "created_at": item.created_at,
                }
                for item in report.versions
            ],
            "current_version": report.current_version,
            "created_at": report.created_at,
            "updated_at": report.updated_at,
        }

    @staticmethod
    def _decode(raw: dict[str, object]) -> DailyReport:
        sources_raw = raw["source_chat_snapshot"]
        versions_raw = raw["versions"]
        if not isinstance(sources_raw, list) or not isinstance(versions_raw, list):
            raise ReportValidationError("日报文件列表字段无效")
        sources = tuple(
            ReportSourceMessage(role=item["role"], content=item["content"])
            for item in sources_raw
            if isinstance(item, dict)
        )
        versions = tuple(
            ReportVersion(
                number=int(item["number"]),
                sections=ReportSections.from_mapping(item["sections"]),
                kind=item["kind"],
                instruction=item.get("instruction"),
                created_at=float(item["created_at"]),
            )
            for item in versions_raw
            if isinstance(item, dict)
        )
        return DailyReport.create(
            report_date=str(raw["date"]),
            source_notes=str(raw["source_notes"]),
            source_session_id=None if raw["source_session_id"] is None else str(raw["source_session_id"]),
            source_chat_snapshot=sources,
            versions=versions,
            current_version=int(raw["current_version"]),
            created_at=float(raw["created_at"]),
            updated_at=float(raw["updated_at"]),
        )
