from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import threading
import time
from typing import Iterator, Literal
from uuid import UUID, uuid4

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - exercised on non-Windows deployments
    import fcntl

from iris_agent.reports.errors import (
    ReportAttachmentInvalidTypeError,
    ReportAttachmentNotFoundError,
    ReportAttachmentStorageError,
    ReportAttachmentTooLargeError,
    ReportAttachmentTooManyError,
    ReportAttachmentTotalTooLargeError,
    ReportValidationError,
)


_ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ".pdf": frozenset({"application/pdf"}),
    ".md": frozenset({"text/markdown"}),
    ".txt": frozenset({"text/plain"}),
    ".xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ".xls": frozenset({"application/vnd.ms-excel"}),
    ".png": frozenset({"image/png"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".webp": frozenset({"image/webp"}),
}
_AttachmentStatus = Literal["temporary", "preserved"]
_AttachmentExtractionStatus = Literal["pending", "ready", "unavailable", "failed"]
_INDEX_FILENAME = "index.json"
_LOCK_FILENAME = ".attachments.lock"
_LOCK_GUARD_FILENAME = ".attachments.guard"
_LOCK_LEASE_SECONDS = 60.0
_INDEX_RECORD_REQUIRED_KEYS = {
    "id", "original_name", "media_type", "size_bytes", "preserve",
    "status", "extracted_text", "created_at", "file_name",
}
_INDEX_RECORD_OPTIONAL_KEYS = {"extraction_status", "extraction_message"}


@dataclass(frozen=True, slots=True)
class ReportAttachment:
    id: str
    original_name: str
    media_type: str
    size_bytes: int
    preserve: bool
    status: _AttachmentStatus
    extracted_text: str | None = None
    created_at: float = field(default_factory=time.time)
    extraction_status: _AttachmentExtractionStatus | None = None
    extraction_message: str | None = None

    def __post_init__(self) -> None:
        try:
            UUID(self.id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("attachment id must be a UUID") from exc
        if not isinstance(self.original_name, str) or not self.original_name or Path(self.original_name).name != self.original_name:
            raise ValueError("attachment name must be a basename")
        if (
            not isinstance(self.media_type, str)
            or not self.media_type.strip()
            or not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 1
            or not isinstance(self.created_at, (int, float))
            or isinstance(self.created_at, bool)
            or not math.isfinite(self.created_at)
        ):
            raise ValueError("attachment metadata is invalid")
        if not isinstance(self.preserve, bool) or self.status not in {"temporary", "preserved"}:
            raise ValueError("attachment status is invalid")
        if self.preserve != (self.status == "preserved"):
            raise ValueError("attachment preserve state is inconsistent")
        extraction_status = self.extraction_status
        if extraction_status is None:
            extraction_status = "ready" if self.extracted_text else "pending"
            object.__setattr__(self, "extraction_status", extraction_status)
        if extraction_status not in {"pending", "ready", "unavailable", "failed"}:
            raise ValueError("attachment extraction status is invalid")
        if self.extraction_message is not None and (
            not isinstance(self.extraction_message, str)
            or not self.extraction_message.strip()
            or len(self.extraction_message) > 200
            or "\n" in self.extraction_message
            or "\r" in self.extraction_message
        ):
            raise ValueError("attachment extraction message is invalid")
        if extraction_status == "ready":
            if not isinstance(self.extracted_text, str) or not self.extracted_text.strip() or self.extraction_message is not None:
                raise ValueError("attachment extraction result is inconsistent")
        elif self.extracted_text is not None or extraction_status == "pending" and self.extraction_message is not None:
            raise ValueError("attachment extraction result is inconsistent")


class AttachmentFile:
    """Read-only attachment handle pinned to the verified file descriptor."""

    def __init__(self, path: Path, descriptor: int):
        self._path = path
        self._descriptor = descriptor

    @property
    def parent(self) -> Path:
        return self._path.parent

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def suffix(self) -> str:
        return self._path.suffix

    def exists(self) -> bool:
        try:
            os.fstat(self._descriptor)
        except OSError:
            return False
        return True

    def read_bytes(self) -> bytes:
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        remaining = os.fstat(self._descriptor).st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(self._descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1

    def __del__(self) -> None:
        self.close()


class AttachmentRepository:
    def __init__(self, root: str | Path, max_file_bytes: int, max_total_bytes: int, max_count: int):
        if min(max_file_bytes, max_total_bytes, max_count) < 1:
            raise ReportValidationError("日报附件限制必须大于 0")
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self._root = self.root.resolve()
        except OSError as exc:
            raise ReportAttachmentStorageError("无法准备日报附件存储") from exc
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_count = max_count
        self._attachments: dict[str, ReportAttachment] = {}
        self._paths: dict[str, Path] = {}
        self._dates: dict[str, str] = {}
        self._lock = threading.RLock()
        self._load_preserved_attachments()

    def save(self, report_date: str, original_name: str, content: bytes, media_type: str, preserve: bool) -> ReportAttachment:
        self._validate_date(report_date)
        safe_name = self._safe_basename(original_name)
        suffix = Path(safe_name).suffix.lower()
        self._validate_upload(suffix, content, media_type, preserve)
        if len(content) > self.max_file_bytes:
            raise ReportAttachmentTooLargeError("日报附件超过单文件大小限制")

        with self._lock:
            with self._date_lock(report_date):
                self._refresh_for_date(report_date)
                existing = self._list_for_date(report_date)
                if len(existing) >= self.max_count:
                    raise ReportAttachmentTooManyError("日报附件数量超过限制")
                if sum(item.size_bytes for item in existing) + len(content) > self.max_total_bytes:
                    raise ReportAttachmentTotalTooLargeError("日报附件总大小超过限制")

                attachment_id = str(uuid4())
                directory = self._directory_for(report_date, preserve)
                target = directory / f"{attachment_id}{suffix}"
                try:
                    directory = self._directory_for(report_date, preserve)
                    target = directory / f"{attachment_id}{suffix}"
                    target.write_bytes(content)
                    self._controlled_file(report_date, preserve, target)
                    attachment = ReportAttachment(
                        id=attachment_id,
                        original_name=safe_name,
                        media_type=media_type,
                        size_bytes=len(content),
                        preserve=preserve,
                        status="preserved" if preserve else "temporary",
                    )
                    self._register(report_date, attachment, target)
                    self._write_index(report_date, preserve)
                    return attachment
                except (OSError, TypeError, ValueError, ReportAttachmentStorageError) as exc:
                    self._unregister(attachment_id)
                    self._remove_saved_file(report_date, preserve, target)
                    raise ReportAttachmentStorageError("无法保存日报附件") from exc

    def list_for_date(self, report_date: str) -> list[ReportAttachment]:
        self._validate_date(report_date)
        with self._lock:
            with self._date_lock(report_date):
                self._refresh_for_date(report_date)
                return self._list_for_date(report_date)

    def path_for(self, attachment_id: str) -> AttachmentFile:
        with self._lock:
            report_date = self._dates.get(attachment_id)
            if report_date is None:
                raise ReportAttachmentNotFoundError("日报附件不存在")
            with self._date_lock(report_date):
                self._refresh_for_date(report_date)
                attachment = self._attachments.get(attachment_id)
                path = self._paths.get(attachment_id)
                if attachment is None or path is None or not path.exists():
                    raise ReportAttachmentNotFoundError("日报附件不存在")
                self._controlled_file(report_date, attachment.preserve, path)
                return AttachmentFile(path, self._open_controlled_file(report_date, attachment.preserve, path))

    def cleanup(self, attachment_ids: list[str] | tuple[str, ...]) -> None:
        for attachment_id in attachment_ids:
            with self._lock:
                attachment = self._attachments.get(attachment_id)
            if attachment is not None and not attachment.preserve:
                self.delete(attachment_id)

    def delete(self, attachment_id: str) -> None:
        with self._lock:
            report_date = self._dates.get(attachment_id)
            if report_date is None:
                raise ReportAttachmentNotFoundError("日报附件不存在")
            with self._date_lock(report_date):
                self._refresh_for_date(report_date)
                self._delete(attachment_id)

    def set_extracted_text(self, attachment_id: str, extracted_text: str) -> ReportAttachment:
        if not isinstance(extracted_text, str):
            raise ReportAttachmentStorageError("无法保存日报附件提取文本")
        return self.set_extraction_result(
            attachment_id,
            extraction_status="ready",
            extracted_text=extracted_text,
        )

    def set_extraction_result(
        self,
        attachment_id: str,
        *,
        extraction_status: _AttachmentExtractionStatus,
        extracted_text: str | None = None,
        extraction_message: str | None = None,
    ) -> ReportAttachment:
        with self._lock:
            report_date = self._dates.get(attachment_id)
            if report_date is None:
                raise ReportAttachmentNotFoundError("日报附件不存在")
            with self._date_lock(report_date):
                self._refresh_for_date(report_date)
                current = self._attachments.get(attachment_id)
                path = self._paths.get(attachment_id)
                if current is None or path is None:
                    raise ReportAttachmentNotFoundError("日报附件不存在")
                try:
                    updated = replace(
                        current,
                        extraction_status=extraction_status,
                        extracted_text=extracted_text,
                        extraction_message=extraction_message,
                    )
                except (TypeError, ValueError) as exc:
                    raise ReportAttachmentStorageError("无法保存日报附件提取结果") from exc
                self._register(report_date, updated, path)
                try:
                    self._write_index(report_date, updated.preserve)
                except ReportAttachmentStorageError:
                    self._register(report_date, current, path)
                    raise
                return updated

    def _delete(self, attachment_id: str) -> None:
        attachment = self._attachments.get(attachment_id)
        path = self._paths.get(attachment_id)
        report_date = self._dates.get(attachment_id)
        if attachment is None or path is None or report_date is None:
            raise ReportAttachmentNotFoundError("日报附件不存在")
        self._controlled_file(report_date, attachment.preserve, path)
        if attachment.preserve:
            try:
                self._write_index(report_date, True, exclude_id=attachment_id)
                path.unlink(missing_ok=True)
            except OSError as exc:
                try:
                    self._write_index(report_date, True)
                except ReportAttachmentStorageError:
                    pass
                raise ReportAttachmentStorageError("无法删除日报附件") from exc
        else:
            try:
                self._write_index(report_date, False, exclude_id=attachment_id)
                path.unlink(missing_ok=True)
            except OSError as exc:
                try:
                    self._write_index(report_date, False)
                except ReportAttachmentStorageError:
                    pass
                raise ReportAttachmentStorageError("无法删除日报附件") from exc
        self._unregister(attachment_id)

    def _load_preserved_attachments(self) -> None:
        try:
            for date_directory in self._root.glob("????-??-??"):
                report_date = date_directory.name
                self._validate_date(report_date)
                self._refresh_for_date(report_date)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ReportAttachmentStorageError("无法读取日报附件索引") from exc

    def _refresh_for_date(self, report_date: str) -> None:
        for attachment_id, attachment in list(self._attachments.items()):
            if self._dates[attachment_id] == report_date:
                self._unregister(attachment_id)
        for preserve in (True, False):
            directory = self._directory_for(report_date, preserve=preserve, create=False)
            index_path = directory / _INDEX_FILENAME
            if index_path.exists():
                try:
                    self._load_index(report_date, directory, index_path, preserve)
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ReportAttachmentStorageError("无法读取日报附件索引") from exc

    def _load_index(self, report_date: str, directory: Path, index_path: Path, preserve: bool) -> None:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) != {"attachments"} or not isinstance(raw["attachments"], list):
            raise ValueError("invalid attachment index")
        for record in raw["attachments"]:
            attachment, target = self._decode_record(report_date, directory, record)
            if attachment.preserve != preserve:
                raise ValueError("attachment index has wrong lifecycle")
            self._register(report_date, attachment, target)

    def _decode_record(self, report_date: str, directory: Path, record: object) -> tuple[ReportAttachment, Path]:
        if (
            not isinstance(record, dict)
            or not _INDEX_RECORD_REQUIRED_KEYS <= set(record)
            or not set(record) <= _INDEX_RECORD_REQUIRED_KEYS | _INDEX_RECORD_OPTIONAL_KEYS
        ):
            raise ValueError("invalid attachment record")
        attachment_id = record["id"]
        original_name = record["original_name"]
        media_type = record["media_type"]
        size_bytes = record["size_bytes"]
        preserve = record["preserve"]
        status = record["status"]
        extracted_text = record["extracted_text"]
        created_at = record["created_at"]
        file_name = record["file_name"]
        extraction_status = record.get("extraction_status")
        extraction_message = record.get("extraction_message")
        if (
            not isinstance(attachment_id, str)
            or not isinstance(original_name, str)
            or not isinstance(media_type, str)
            or not isinstance(size_bytes, int) or isinstance(size_bytes, bool)
            or not isinstance(preserve, bool)
            or not isinstance(status, str)
            or extracted_text is not None and not isinstance(extracted_text, str)
            or not isinstance(created_at, (int, float)) or isinstance(created_at, bool)
            or not isinstance(file_name, str)
            or extraction_status is not None and not isinstance(extraction_status, str)
            or extraction_message is not None and not isinstance(extraction_message, str)
            or Path(file_name).name != file_name
        ):
            raise ValueError("invalid attachment file name")
        suffix = Path(file_name).suffix.lower()
        attachment = ReportAttachment(
            id=attachment_id,
            original_name=original_name,
            media_type=media_type,
            size_bytes=size_bytes,
            preserve=preserve,
            status=status,
            extracted_text=extracted_text,
            created_at=created_at,
            extraction_status=extraction_status,
            extraction_message=extraction_message,
        )
        if suffix not in _ALLOWED_MEDIA_TYPES or attachment.media_type not in _ALLOWED_MEDIA_TYPES[suffix]:
            raise ValueError("invalid attachment record")
        expected_name = f"{attachment.id}{suffix}"
        if file_name != expected_name:
            raise ValueError("invalid attachment file name")
        target = directory / file_name
        if target.parent != directory or not target.exists() or target.stat().st_size != attachment.size_bytes:
            raise ValueError("invalid attachment file")
        self._controlled_file(report_date, attachment.preserve, target)
        return attachment, target

    def _write_index(self, report_date: str, preserve: bool, exclude_id: str | None = None) -> None:
        directory = self._directory_for(report_date, preserve=preserve)
        records = []
        for attachment in self._list_for_date(report_date):
            if attachment.preserve == preserve and attachment.id != exclude_id:
                path = self._paths[attachment.id]
                records.append({
                    "id": attachment.id,
                    "original_name": attachment.original_name,
                    "media_type": attachment.media_type,
                    "size_bytes": attachment.size_bytes,
                    "preserve": attachment.preserve,
                    "status": attachment.status,
                    "extracted_text": attachment.extracted_text,
                    "created_at": attachment.created_at,
                    "extraction_status": attachment.extraction_status,
                    "extraction_message": attachment.extraction_message,
                    "file_name": path.name,
                })
        temporary_path: Path | None = None
        try:
            directory = self._directory_for(report_date, preserve)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp") as handle:
                temporary_path = Path(handle.name)
                json.dump({"attachments": records}, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, directory / _INDEX_FILENAME)
            self._controlled_file(report_date, preserve, directory / _INDEX_FILENAME)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None:
                self._remove_new_file(temporary_path)
            raise ReportAttachmentStorageError("无法保存日报附件索引") from exc

    def _register(self, report_date: str, attachment: ReportAttachment, path: Path) -> None:
        self._attachments[attachment.id] = attachment
        self._paths[attachment.id] = path
        self._dates[attachment.id] = report_date

    def _unregister(self, attachment_id: str) -> None:
        self._attachments.pop(attachment_id, None)
        self._paths.pop(attachment_id, None)
        self._dates.pop(attachment_id, None)

    def _list_for_date(self, report_date: str) -> list[ReportAttachment]:
        return [item for item_id, item in self._attachments.items() if self._dates[item_id] == report_date]

    @staticmethod
    def _validate_upload(suffix: str, content: bytes, media_type: object, preserve: object) -> None:
        if (
            suffix not in _ALLOWED_MEDIA_TYPES
            or not isinstance(content, bytes)
            or not content
            or not isinstance(media_type, str)
            or media_type not in _ALLOWED_MEDIA_TYPES[suffix]
            or not isinstance(preserve, bool)
        ):
            raise ReportAttachmentInvalidTypeError("不支持该日报附件")

    @staticmethod
    def _validate_date(report_date: str) -> None:
        try:
            parsed = date.fromisoformat(report_date)
        except (TypeError, ValueError) as exc:
            raise ReportValidationError("日报日期必须使用 YYYY-MM-DD 格式", code="report_invalid_date") from exc
        if parsed.isoformat() != report_date:
            raise ReportValidationError("日报日期必须使用 YYYY-MM-DD 格式", code="report_invalid_date")

    @staticmethod
    def _safe_basename(original_name: str) -> str:
        if not isinstance(original_name, str):
            raise ReportAttachmentInvalidTypeError("不支持该日报附件")
        name = PureWindowsPath(original_name).name
        name = PurePosixPath(name).name.strip()
        if not name or name in {".", ".."}:
            raise ReportAttachmentInvalidTypeError("不支持该日报附件")
        return name

    @staticmethod
    def _remove_new_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _remove_saved_file(self, report_date: str, preserve: bool, path: Path) -> None:
        try:
            self._controlled_file(report_date, preserve, path)
        except ReportAttachmentStorageError:
            return
        self._remove_new_file(path)

    @contextmanager
    def _date_lock(self, report_date: str) -> Iterator[None]:
        date_directory = self._date_directory(report_date, create=True)
        lock_path = date_directory / _LOCK_FILENAME
        guard_path = date_directory / _LOCK_GUARD_FILENAME
        deadline = time.monotonic() + 10.0
        token = str(uuid4())
        guard = self._acquire_guard(guard_path, deadline)
        try:
            if lock_path.exists() and not self._reclaim_stale_lock(lock_path):
                raise ReportAttachmentStorageError("无法锁定日报附件存储")
            descriptor = os.open(lock_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
            payload = json.dumps({"pid": os.getpid(), "created_at": time.time(), "token": token}).encode("utf-8")
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            yield
        finally:
            try:
                current = json.loads(lock_path.read_text(encoding="utf-8"))
                if isinstance(current, dict) and current.get("token") == token:
                    lock_path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            self._release_guard(guard)

    def _reclaim_stale_lock(self, lock_path: Path) -> bool:
        try:
            raw = json.loads(lock_path.read_text(encoding="utf-8"))
            pid = raw.get("pid") if isinstance(raw, dict) else None
            created_at = raw.get("created_at") if isinstance(raw, dict) else None
            if (
                not isinstance(pid, int)
                or isinstance(pid, bool)
                or not isinstance(created_at, (int, float))
                or isinstance(created_at, bool)
                or not math.isfinite(created_at)
                or time.time() - created_at <= _LOCK_LEASE_SECONDS
                or self._pid_is_alive(pid)
            ):
                return False
            lock_path.unlink()
            return True
        except (ValueError, TypeError, json.JSONDecodeError):
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_LEASE_SECONDS:
                    lock_path.unlink()
                    return True
            except OSError:
                return False
            return False
        except OSError:
            return False

    def _acquire_guard(self, guard_path: Path, deadline: float) -> int:
        try:
            descriptor = os.open(guard_path, os.O_CREAT | os.O_RDWR)
            if os.path.getsize(guard_path) == 0:
                os.write(descriptor, b"0")
                os.fsync(descriptor)
        except OSError as exc:
            raise ReportAttachmentStorageError("无法锁定日报附件存储") from exc
        while True:
            try:
                if os.name == "nt":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - exercised on non-Windows deployments
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(descriptor)
                    raise ReportAttachmentStorageError("无法锁定日报附件存储")
                time.sleep(0.01)

    @staticmethod
    def _release_guard(descriptor: int) -> None:
        try:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised on non-Windows deployments
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        if pid < 1:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _date_directory(self, report_date: str, create: bool) -> Path:
        expected = self._root / report_date
        try:
            if create:
                expected.mkdir(parents=True, exist_ok=True)
            resolved = expected.resolve()
        except OSError as exc:
            raise ReportAttachmentStorageError("无法访问日报附件存储") from exc
        if resolved != expected or self._root not in expected.parents:
            raise ReportAttachmentStorageError("无法访问日报附件存储")
        return expected

    def _directory_for(self, report_date: str, preserve: bool, create: bool = True) -> Path:
        name = "attachments" if preserve else "temporary"
        date_directory = self._date_directory(report_date, create=create)
        expected = date_directory / name
        try:
            if create:
                expected.mkdir(parents=True, exist_ok=True)
            resolved = expected.resolve()
        except OSError as exc:
            raise ReportAttachmentStorageError("无法访问日报附件存储") from exc
        if resolved != expected or self._root not in expected.parents:
            raise ReportAttachmentStorageError("无法访问日报附件存储")
        return expected

    def _controlled_file(self, report_date: str, preserve: bool, path: Path) -> Path:
        directory = self._directory_for(report_date, preserve, create=False)
        expected = directory / path.name
        if path != expected:
            raise ReportAttachmentStorageError("无法访问日报附件存储")
        try:
            resolved_directory = directory.resolve(strict=True)
            resolved_file = path.resolve(strict=True)
        except OSError as exc:
            raise ReportAttachmentStorageError("无法访问日报附件存储") from exc
        if (
            resolved_directory != directory
            or self._root not in resolved_directory.parents
            or resolved_file.parent != resolved_directory
            or self._root not in resolved_file.parents
        ):
            raise ReportAttachmentStorageError("无法访问日报附件存储")
        return path

    def _open_controlled_file(self, report_date: str, preserve: bool, path: Path) -> int:
        self._controlled_file(report_date, preserve, path)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        except OSError as exc:
            raise ReportAttachmentStorageError("无法访问日报附件存储") from exc
        try:
            self._controlled_file(report_date, preserve, path)
            if os.fstat(descriptor).st_size != path.stat().st_size:
                raise ReportAttachmentStorageError("无法访问日报附件存储")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

