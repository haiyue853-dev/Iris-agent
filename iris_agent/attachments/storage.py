from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import threading
from typing import Callable, Iterator
from dataclasses import replace
from uuid import uuid4

from .errors import (
    AttachmentInvalidTypeError,
    AttachmentNotFoundError,
    AttachmentStorageError,
    AttachmentTooLargeError,
    AttachmentTooManyError,
)
from .models import AttachmentMetadata


_ALLOWED_MEDIA_TYPES = {
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pdf": {"application/pdf"}, ".md": {"text/markdown"}, ".txt": {"text/plain"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel"}, ".png": {"image/png"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".webp": {"image/webp"},
}


class AttachmentFile:
    """Read-only handle backed by a descriptor opened after path validation."""

    def __init__(self, path: Path, descriptor: int, original_name: str):
        self._path, self._descriptor, self._original_name = path, descriptor, original_name

    @property
    def name(self) -> str: return self._path.name

    @property
    def original_name(self) -> str: return self._original_name

    @property
    def suffix(self) -> str: return self._path.suffix

    @property
    def parent(self) -> Path: return self._path.parent

    def exists(self) -> bool:
        try: os.fstat(self._descriptor)
        except OSError: return False
        return True

    def read_bytes(self) -> bytes:
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while chunk := os.read(self._descriptor, 1024 * 1024): chunks.append(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1

    def __del__(self) -> None: self.close()


class AttachmentStorage:
    def __init__(self, root: str | Path, max_file_bytes: int, max_total_bytes: int, max_count: int, temporary_ttl: timedelta = timedelta(days=1)):
        if min(max_file_bytes, max_total_bytes, max_count) < 1:
            raise ValueError("attachment limits must be positive")
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self._root = self.root.resolve()
        except OSError as exc: raise AttachmentStorageError("无法准备附件存储") from exc
        self.max_file_bytes, self.max_total_bytes, self.max_count = max_file_bytes, max_total_bytes, max_count
        self.temporary_ttl = temporary_ttl
        self._lock = threading.RLock()

    def save(self, scope_id: str, original_name: str, content: bytes, media_type: str) -> AttachmentMetadata:
        scope = self._scope(scope_id); name = self._safe_basename(original_name); suffix = Path(name).suffix.lower()
        if suffix not in _ALLOWED_MEDIA_TYPES or media_type not in _ALLOWED_MEDIA_TYPES[suffix] or not content:
            raise AttachmentInvalidTypeError("不支持该附件类型")
        if len(content) > self.max_file_bytes: raise AttachmentTooLargeError("附件超过单文件大小限制")
        with self._lock:
            directory = self._directory(scope, create=True)
            with self._directory_lock(directory):
                records = self._load(scope, directory)
                if len(records) >= self.max_count: raise AttachmentTooManyError("附件数量超过限制")
                if sum(item[0].size_bytes for item in records) + len(content) > self.max_total_bytes:
                    raise AttachmentTooLargeError("附件总大小超过限制")
                attachment_id = str(uuid4()); file_name = f"{attachment_id}{suffix}"; target = directory / file_name
                metadata = AttachmentMetadata(attachment_id, scope, name, media_type, len(content), datetime.now(timezone.utc), "pending")
                try:
                    self._write_bytes_exclusive(target, content)
                    self._write_index(directory, records + [(metadata, file_name)])
                except OSError as exc:
                    target.unlink(missing_ok=True)
                    raise AttachmentStorageError("无法保存附件") from exc
                return metadata

    def list(self, scope_id: str) -> list[AttachmentMetadata]:
        scope = self._scope(scope_id)
        with self._lock:
            directory = self._directory(scope, create=False)
            return [metadata for metadata, _ in self._load(scope, directory)]

    def open(self, scope_id: str, attachment_id: str) -> AttachmentFile:
        metadata, file_name, directory = self._find(scope_id, attachment_id)
        path = directory / file_name
        try:
            self._controlled(path, directory)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            return AttachmentFile(path, os.open(path, flags), metadata.original_name)
        except OSError as exc: raise AttachmentNotFoundError("附件不存在") from exc

    def delete(self, scope_id: str, attachment_id: str) -> None:
        scope = self._scope(scope_id)
        with self._lock:
            directory = self._directory(scope, create=False)
            with self._directory_lock(directory):
                records = self._load(scope, directory)
                selected = next(((meta, name) for meta, name in records if meta.id == attachment_id), None)
                if selected is None: raise AttachmentNotFoundError("附件不存在")
                path = directory / selected[1]
                try:
                    self._controlled(path, directory)
                    self._write_index(directory, [item for item in records if item[0].id != attachment_id])
                    path.unlink()
                except OSError as exc: raise AttachmentStorageError("无法删除附件") from exc

    def update_extraction_result(
        self, scope_id: str, attachment_id: str, *, extraction_status: str,
        extracted_text: str | None = None, extraction_message: str | None = None,
        text_truncated: bool = False, sources: tuple[str, ...] = (),
    ) -> AttachmentMetadata:
        scope = self._scope(scope_id)
        with self._lock:
            directory = self._directory(scope, create=False)
            with self._directory_lock(directory):
                records = self._load(scope, directory)
                for index, (metadata, file_name) in enumerate(records):
                    if metadata.id != attachment_id:
                        continue
                    try:
                        updated = replace(
                            metadata, extraction_status=extraction_status,
                            extracted_text=extracted_text, extraction_message=extraction_message,
                            text_truncated=text_truncated, sources=sources,
                        )
                    except (TypeError, ValueError) as exc:
                        raise AttachmentStorageError("无法保存附件提取结果") from exc
                    records[index] = (updated, file_name)
                    self._write_index(directory, records)
                    return updated
        raise AttachmentNotFoundError("附件不存在")

    def scope_for(self, attachment_id: str) -> str | None:
        with self._lock:
            try:
                directories = list(self._root.iterdir())
            except OSError as exc:
                raise AttachmentStorageError("无法读取附件索引") from exc
            for scope_directory in directories:
                if not scope_directory.is_dir() or scope_directory.is_symlink():
                    continue
                scope = scope_directory.name
                try:
                    if any(metadata.id == attachment_id for metadata in self.list(scope)):
                        return scope
                except AttachmentStorageError:
                    continue
        return None

    def cleanup_expired(self, is_temporary: Callable[[AttachmentMetadata], bool] | None = None) -> None:
        cutoff = datetime.now(timezone.utc) - self.temporary_ttl
        for scope_dir in self._root.iterdir():
            if not scope_dir.is_dir() or scope_dir.is_symlink(): continue
            scope = scope_dir.name
            try:
                for metadata in self.list(scope):
                    if metadata.created_at < cutoff and (is_temporary is None or is_temporary(metadata)):
                        self.delete(scope, metadata.id)
            except (AttachmentStorageError, AttachmentNotFoundError): continue

    def _find(self, scope_id: str, attachment_id: str) -> tuple[AttachmentMetadata, str, Path]:
        scope = self._scope(scope_id); directory = self._directory(scope, create=False)
        for metadata, file_name in self._load(scope, directory):
            if metadata.id == attachment_id: return metadata, file_name, directory
        raise AttachmentNotFoundError("附件不存在")

    def _scope(self, scope_id: str) -> str:
        if (
            not isinstance(scope_id, str)
            or not scope_id.strip()
            or scope_id in {".", ".."}
            or Path(scope_id).name != scope_id
            or PurePosixPath(scope_id).name != scope_id
            or PureWindowsPath(scope_id).name != scope_id
        ):
            raise AttachmentStorageError("附件范围无效")
        return scope_id

    @staticmethod
    def _safe_basename(name: str) -> str:
        if not isinstance(name, str) or not name.strip(): raise AttachmentInvalidTypeError("附件名称无效")
        cleaned = PurePosixPath(name.replace("\\", "/")).name
        if cleaned in {"", ".", ".."}: raise AttachmentInvalidTypeError("附件名称无效")
        return cleaned

    def _directory(self, scope: str, create: bool) -> Path:
        scope_dir = self._root / scope
        try:
            if scope_dir.is_symlink() or scope_dir.parent.resolve() != self._root:
                raise OSError("unsafe attachment scope")
        except OSError as exc:
            raise AttachmentStorageError("附件目录无效") from exc
        if create:
            try:
                scope_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise AttachmentStorageError("附件目录无效") from exc
            try:
                if scope_dir.is_symlink() or scope_dir.resolve() != scope_dir or scope_dir.parent.resolve() != self._root:
                    raise OSError("unsafe attachment scope")
            except OSError as exc:
                raise AttachmentStorageError("附件目录无效") from exc
        directory = scope_dir / "attachments"
        if create:
            try:
                directory.mkdir(exist_ok=True)
            except OSError as exc:
                raise AttachmentStorageError("附件目录无效") from exc
        try: self._controlled(directory, self._root / scope)
        except OSError as exc: raise AttachmentStorageError("附件目录无效") from exc
        return directory

    @staticmethod
    def _controlled(path: Path, parent: Path) -> None:
        if path.is_symlink() or path.parent.resolve() != parent.resolve(): raise OSError("unsafe attachment path")

    @contextmanager
    def _directory_lock(self, directory: Path) -> Iterator[None]:
        # The process-local lock protects index updates; atomic replace protects readers.
        yield

    def _load(self, scope: str, directory: Path) -> list[tuple[AttachmentMetadata, str]]:
        index = directory / "index.json"
        if not index.exists(): return []
        try:
            payload = json.loads(index.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"attachments"} or not isinstance(payload["attachments"], list): raise ValueError()
            result = []
            for item in payload["attachments"]:
                required = {"id", "scope_id", "original_name", "media_type", "size_bytes", "created_at", "extraction_status", "extraction_message", "text_truncated", "sources", "file_name"}
                if not isinstance(item, dict) or not required <= set(item) <= required | {"extracted_text"}: raise ValueError()
                file_name = item.pop("file_name")
                if not isinstance(file_name, str) or Path(file_name).name != file_name: raise ValueError()
                item["created_at"] = datetime.fromisoformat(item["created_at"])
                item["sources"] = tuple(item["sources"])
                item.setdefault("extracted_text", None)
                metadata = AttachmentMetadata(**item)
                if metadata.scope_id != scope or not (directory / file_name).exists(): raise ValueError()
                self._controlled(directory / file_name, directory)
                result.append((metadata, file_name))
            return result
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc: raise AttachmentStorageError("无法读取附件索引") from exc

    def _write_index(self, directory: Path, records: list[tuple[AttachmentMetadata, str]]) -> None:
        payload = {"attachments": [{"id": item.id, "scope_id": item.scope_id, "original_name": item.original_name, "media_type": item.media_type, "size_bytes": item.size_bytes, "created_at": item.created_at.isoformat(), "extraction_status": item.extraction_status, "extracted_text": item.extracted_text, "extraction_message": item.extraction_message, "text_truncated": item.text_truncated, "sources": list(item.sources), "file_name": file_name} for item, file_name in records]}
        descriptor, temporary = tempfile.mkstemp(prefix=".index-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, directory / "index.json")
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _write_bytes_exclusive(path: Path, content: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle: handle.write(content); handle.flush(); os.fsync(handle.fileno())
