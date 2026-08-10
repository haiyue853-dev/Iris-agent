"""单个 Iris 进程使用的安全本地文档存储。"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import threading
import time
from typing import Any, Callable
from uuid import UUID, uuid4

from iris_agent.documents.errors import (
    DocumentExtractFailedError,
    DocumentInvalidTypeError,
    DocumentNotFoundError,
    DocumentStorageError,
    DocumentTooLargeError,
    DocumentTooManyError,
    DocumentTotalTooLargeError,
    DocumentValidationError,
)
from iris_agent.documents.models import DocumentExtraction, DocumentFile, DocumentRecord, DocumentSource


_ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".txt": frozenset({"text/plain"}),
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ".pdf": frozenset({"application/pdf"}),
    ".xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ".xls": frozenset({"application/vnd.ms-excel"}),
}
_INDEX_KEYS = {
    "id",
    "original_name",
    "suffix",
    "media_type",
    "size_bytes",
    "created_at",
    "extraction_status",
    "extraction_message",
    "text_truncated",
    "sources",
    "file_name",
}
_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SERVER_RAW_NAME = re.compile(
    rf"^(?P<document_id>{_UUID_PATTERN})(?P<suffix>\.txt|\.md|\.docx|\.pdf|\.xlsx|\.xls)$"
)
_SERVER_TEXT_NAME = re.compile(rf"^{_UUID_PATTERN}\.txt$")
_TEMPORARY_NAME = re.compile(r"^\.iris-document-[0-9a-f]{32}\.tmp$")
_LEGACY_TEMPORARY_NAME = re.compile(
    rf"^\.(?:index\.json|{_UUID_PATTERN}(?:\.txt|\.md|\.docx|\.pdf|\.xlsx|\.xls)?)\.[0-9a-f]{{32}}\.tmp$"
)


class DocumentRepository:
    """文件、提取文本和元数据均限制在一个受控根目录内。

    该仓库只保证单个 Iris 服务进程中的并发安全；它故意不实现跨进程锁。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_file_bytes: int,
        max_total_bytes: int,
        max_count: int,
        max_text_chars: int,
    ):
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in (max_file_bytes, max_total_bytes, max_count, max_text_chars)
        ):
            raise DocumentValidationError("文档存储限制必须大于 0")
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_count = max_count
        self.max_text_chars = max_text_chars
        self._lock = threading.RLock()
        self._records: dict[str, DocumentRecord] = {}
        self._total_bytes = 0
        try:
            requested_root = Path(root)
            requested_root.mkdir(parents=True, exist_ok=True)
            if requested_root.is_symlink():
                raise OSError("symlinked root")
            self.root = requested_root.absolute()
            self._root = self.root.resolve(strict=True)
            if self.root != self._root:
                raise OSError("root escapes controlled directory")
            self._files_directory = self._prepare_directory("files")
            self._text_directory = self._prepare_directory("text")
            self._index_path = self._root / "index.json"
            self._load()
        except DocumentStorageError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DocumentStorageError("无法准备文档存储") from exc

    def save(self, original_name: str, content: bytes, media_type: str) -> DocumentRecord:
        """保存原文并返回 pending 元数据；提取由服务层负责。"""
        safe_name, suffix, canonical_media_type = self._validate_upload(original_name, content, media_type)
        size_bytes = len(content)
        if size_bytes > self.max_file_bytes:
            raise DocumentTooLargeError("文档超过单文件大小限制")

        with self._lock:
            if len(self._records) >= self.max_count:
                raise DocumentTooManyError("文档数量超过限制")
            if self._total_bytes + size_bytes > self.max_total_bytes:
                raise DocumentTotalTooLargeError("文档总大小超过限制")
            document = DocumentRecord(
                id=str(uuid4()),
                original_name=safe_name,
                suffix=suffix,
                media_type=canonical_media_type,
                size_bytes=size_bytes,
                created_at=time.time(),
            )
            target = self._raw_path(document)
            try:
                self._atomic_write_bytes(target, content)
                self._assert_controlled_file(target, self._files_directory, expected_size=size_bytes)
                self._records[document.id] = document
                self._total_bytes += size_bytes
                self._write_index()
                return document
            except DocumentStorageError:
                if self._records.pop(document.id, None) is not None:
                    self._total_bytes -= size_bytes
                self._remove_new_file(target)
                raise
            except (OSError, TypeError, ValueError) as exc:
                if self._records.pop(document.id, None) is not None:
                    self._total_bytes -= size_bytes
                self._remove_new_file(target)
                raise DocumentStorageError("无法保存文档") from exc

    def list(self) -> list[DocumentRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda item: (item.created_at, item.id))

    def get(self, document_id: str) -> DocumentRecord:
        with self._lock:
            return self._require(document_id)

    def file_for(self, document_id: str) -> DocumentFile:
        with self._lock:
            document = self._require(document_id)
            self._assert_controlled_file(self._raw_path(document), self._files_directory, expected_size=document.size_bytes)
            return DocumentFile(
                name=document.original_name,
                suffix=document.suffix,
                reader=lambda: self._read_raw_bytes(document_id),
            )

    def read_text(self, document_id: str) -> str:
        with self._lock:
            document = self._require(document_id)
            if document.extraction_status != "ready":
                raise DocumentExtractFailedError("文档文本尚不可用")
            content = self._read_controlled_bytes(self._text_path(document), self._text_directory)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DocumentStorageError("文档提取文本已损坏") from exc
            if not text.strip() or len(text) > self.max_text_chars:
                raise DocumentStorageError("文档提取文本已损坏")
            return text

    def update_extraction(
        self,
        document_id: str,
        extraction: DocumentExtraction | None,
        *,
        message: str | None = None,
    ) -> DocumentRecord:
        """将 pending 文档标记为 ready 或 failed，并独立持久化正文。"""
        with self._lock:
            current = self._require(document_id)
            if current.extraction_status != "pending":
                raise DocumentValidationError("文档提取结果已确定")
            if extraction is None:
                safe_message = self._safe_failure_message(message)
                updated = replace(
                    current,
                    extraction_status="failed",
                    extraction_message=safe_message,
                    text_truncated=False,
                    sources=(),
                )
                self._records[document_id] = updated
                try:
                    self._write_index()
                    return updated
                except DocumentStorageError:
                    self._records[document_id] = current
                    raise

            if message is not None:
                raise DocumentValidationError("成功的提取结果不能包含错误信息")
            if len(extraction.text) > self.max_text_chars:
                raise DocumentValidationError("提取文本超过限制")
            if any(source.file_name != current.original_name for source in extraction.sources):
                raise DocumentValidationError("文档来源无效")
            updated = replace(
                current,
                extraction_status="ready",
                extraction_message=None,
                text_truncated=extraction.truncated,
                sources=extraction.sources,
            )
            target = self._text_path(current)
            try:
                self._atomic_write_bytes(target, extraction.text.encode("utf-8"))
                self._assert_controlled_file(target, self._text_directory)
                self._records[document_id] = updated
                self._write_index()
                return updated
            except DocumentStorageError:
                self._records[document_id] = current
                self._remove_new_file(target)
                raise
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                self._records[document_id] = current
                self._remove_new_file(target)
                raise DocumentStorageError("无法保存文档提取文本") from exc

    def delete(self, document_id: str) -> None:
        with self._lock:
            document = self._require(document_id)
            raw_path = self._raw_path(document)
            text_path = self._text_path(document)
            self._assert_controlled_file(raw_path, self._files_directory, expected_size=document.size_bytes)
            if document.extraction_status == "ready":
                self._assert_controlled_file(text_path, self._text_directory)
            previous = self._records.copy()
            previous_total = self._total_bytes
            self._records.pop(document_id)
            self._total_bytes -= document.size_bytes
            try:
                self._write_index()
                if document.extraction_status == "ready":
                    self._unlink_controlled(text_path, self._text_directory)
                self._unlink_controlled(raw_path, self._files_directory)
            except DocumentStorageError:
                self._records = previous
                self._total_bytes = previous_total
                try:
                    self._write_index()
                except DocumentStorageError:
                    pass
                raise

    def _load(self) -> None:
        with self._lock:
            if self._index_path.is_symlink():
                raise DocumentStorageError("无法访问文档存储")
            if not self._index_path.exists():
                self._validate_directory_contents(self._files_directory, set())
                self._validate_directory_contents(self._text_directory, set())
                self._records = {}
                self._total_bytes = 0
                self._write_index()
                return
            self._assert_controlled_file(self._index_path, self._root)
            try:
                raw = json.loads(self._read_controlled_bytes(self._index_path, self._root).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DocumentStorageError("无法读取文档索引") from exc
            if not isinstance(raw, dict) or set(raw) != {"documents"} or not isinstance(raw["documents"], list):
                raise DocumentStorageError("无法读取文档索引")
            records: dict[str, DocumentRecord] = {}
            for encoded in raw["documents"]:
                document = self._decode_record(encoded)
                if document.id in records:
                    raise DocumentStorageError("无法读取文档索引")
                records[document.id] = document

            total, raw_names, text_names = self._validate_registered_records(records)
            recovery_candidates = self._scan_recovery_candidates(records)
            self._cleanup_recovery_candidates(recovery_candidates)
            self._validate_directory_contents(self._files_directory, raw_names)
            self._validate_directory_contents(self._text_directory, text_names)
            self._records = records
            self._total_bytes = total
            self._recover_interrupted_pending_documents()

    def _validate_registered_records(
        self, records: dict[str, DocumentRecord]
    ) -> tuple[int, set[str], set[str]]:
        """无副作用地验证所有 index 已登记文件，失败时不得进行恢复删除。"""
        total = 0
        raw_names: set[str] = set()
        text_names: set[str] = set()
        for document in records.values():
            self._assert_controlled_file(
                self._raw_path(document), self._files_directory, expected_size=document.size_bytes
            )
            raw_names.add(self._raw_path(document).name)
            if document.extraction_status == "ready":
                text_path = self._text_path(document)
                text = self._read_controlled_bytes(text_path, self._text_directory)
                try:
                    decoded = text.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise DocumentStorageError("文档提取文本已损坏") from exc
                if not decoded.strip() or len(decoded) > self.max_text_chars:
                    raise DocumentStorageError("文档提取文本已损坏")
                text_names.add(text_path.name)
            total += document.size_bytes
        if len(records) > self.max_count or total > self.max_total_bytes:
            raise DocumentStorageError("文档存储配额已损坏")
        return total, raw_names, text_names

    def _scan_recovery_candidates(self, records: dict[str, DocumentRecord]) -> list[tuple[Path, Path]]:
        """先扫描并验证所有可删除残留，再由调用方统一删除，避免部分恢复。"""
        registered_raw_names = {self._raw_path(document).name for document in records.values()}
        registered_text_names = {
            self._text_path(document).name
            for document in records.values()
            if document.extraction_status == "ready"
        }
        return (
            self._scan_root_recovery_candidates()
            + self._scan_directory_recovery_candidates(
                self._files_directory,
                registered_raw_names,
                self._is_server_raw_name,
            )
            + self._scan_directory_recovery_candidates(
                self._text_directory,
                registered_text_names,
                self._is_server_text_name,
            )
        )

    def _scan_root_recovery_candidates(self) -> list[tuple[Path, Path]]:
        try:
            children = list(self._root.iterdir())
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        expected_directories = {"files", "text"}
        candidates: list[tuple[Path, Path]] = []
        for child in children:
            if child.name == "index.json":
                continue
            if child.name in expected_directories:
                if child.is_symlink() or not child.is_dir():
                    raise DocumentStorageError("无法访问文档存储")
                continue
            if self._is_temporary_name(child.name):
                self._assert_controlled_file(child, self._root)
                candidates.append((child, self._root))
                continue
            raise DocumentStorageError("文档存储包含未登记文件")
        return candidates

    def _scan_directory_recovery_candidates(
        self,
        directory: Path,
        registered_names: set[str],
        is_server_name: Callable[[str], bool],
    ) -> list[tuple[Path, Path]]:
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        candidates: list[tuple[Path, Path]] = []
        for child in children:
            if child.name in registered_names:
                continue
            if self._is_temporary_name(child.name) or is_server_name(child.name):
                self._assert_controlled_file(child, directory)
                candidates.append((child, directory))
                continue
            raise DocumentStorageError("文档存储包含未登记文件")
        return candidates

    def _cleanup_recovery_candidates(self, candidates: list[tuple[Path, Path]]) -> None:
        for path, directory in candidates:
            self._delete_recoverable_file(path, directory)

    def _recover_interrupted_pending_documents(self) -> None:
        pending = [document for document in self._records.values() if document.extraction_status == "pending"]
        if not pending:
            return
        before = self._records
        self._records = {
            document_id: (
                replace(
                    document,
                    extraction_status="failed",
                    extraction_message="文档提取在服务中断后未完成",
                )
                if document.extraction_status == "pending"
                else document
            )
            for document_id, document in before.items()
        }
        try:
            self._write_index()
        except DocumentStorageError:
            self._records = before
            raise

    def _decode_record(self, encoded: object) -> DocumentRecord:
        if not isinstance(encoded, dict) or set(encoded) != _INDEX_KEYS:
            raise DocumentStorageError("无法读取文档索引")
        sources = encoded["sources"]
        if not isinstance(sources, list):
            raise DocumentStorageError("无法读取文档索引")
        try:
            parsed_sources = tuple(
                DocumentSource(file_name=source["file_name"], location=source["location"])
                for source in sources
                if isinstance(source, dict) and set(source) == {"file_name", "location"}
            )
            if len(parsed_sources) != len(sources):
                raise ValueError("invalid source")
            document = DocumentRecord(
                id=encoded["id"],
                original_name=encoded["original_name"],
                suffix=encoded["suffix"],
                media_type=encoded["media_type"],
                size_bytes=encoded["size_bytes"],
                created_at=encoded["created_at"],
                extraction_status=encoded["extraction_status"],
                extraction_message=encoded["extraction_message"],
                text_truncated=encoded["text_truncated"],
                sources=parsed_sources,
            )
            file_name = encoded["file_name"]
            if not isinstance(file_name, str) or PureWindowsPath(file_name).name != file_name or PurePosixPath(file_name).name != file_name:
                raise ValueError("invalid file name")
            if file_name != self._raw_path(document).name:
                raise ValueError("invalid file name")
            if document.suffix not in _ALLOWED_MEDIA_TYPES or document.media_type not in _ALLOWED_MEDIA_TYPES[document.suffix]:
                raise ValueError("invalid media type")
            return document
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DocumentStorageError("无法读取文档索引") from exc

    def _write_index(self) -> None:
        payload: dict[str, Any] = {
            "documents": [self._encode_record(record) for record in self.list()],
        }
        try:
            self._atomic_write_bytes(
                self._index_path,
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
            )
            self._assert_controlled_file(self._index_path, self._root)
        except DocumentStorageError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise DocumentStorageError("无法保存文档索引") from exc

    @staticmethod
    def _encode_record(document: DocumentRecord) -> dict[str, Any]:
        return {
            "id": document.id,
            "original_name": document.original_name,
            "suffix": document.suffix,
            "media_type": document.media_type,
            "size_bytes": document.size_bytes,
            "created_at": document.created_at,
            "extraction_status": document.extraction_status,
            "extraction_message": document.extraction_message,
            "text_truncated": document.text_truncated,
            "sources": [
                {"file_name": source.file_name, "location": source.location}
                for source in document.sources
            ],
            "file_name": f"{document.id}{document.suffix}",
        }

    def _prepare_directory(self, name: str) -> Path:
        path = self._root / name
        if path.exists() and path.is_symlink():
            raise DocumentStorageError("无法访问文档存储")
        try:
            path.mkdir(parents=False, exist_ok=True)
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        if path.is_symlink():
            raise DocumentStorageError("无法访问文档存储")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        if resolved != path.absolute() or resolved.parent != self._root or not resolved.is_dir():
            raise DocumentStorageError("无法访问文档存储")
        return resolved

    def _raw_path(self, document: DocumentRecord) -> Path:
        return self._files_directory / f"{document.id}{document.suffix}"

    def _text_path(self, document: DocumentRecord) -> Path:
        return self._text_directory / f"{document.id}.txt"

    def _read_raw_bytes(self, document_id: str) -> bytes:
        with self._lock:
            document = self._require(document_id)
            return self._read_controlled_bytes(
                self._raw_path(document), self._files_directory, expected_size=document.size_bytes
            )

    def _read_controlled_bytes(self, path: Path, directory: Path, *, expected_size: int | None = None) -> bytes:
        self._assert_controlled_file(path, directory, expected_size=expected_size)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        self._assert_controlled_file(path, directory, expected_size=expected_size)
        return data

    def _assert_controlled_file(self, path: Path, directory: Path, *, expected_size: int | None = None) -> None:
        if path.parent != directory or path.is_symlink() or not path.exists() or not path.is_file():
            raise DocumentStorageError("无法访问文档存储")
        try:
            resolved_directory = directory.resolve(strict=True)
            resolved_file = path.resolve(strict=True)
            size = path.stat().st_size
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        if resolved_directory != directory or resolved_file.parent != resolved_directory or not resolved_file.is_file():
            raise DocumentStorageError("无法访问文档存储")
        if expected_size is not None and size != expected_size:
            raise DocumentStorageError("文档文件已损坏")

    def _validate_directory_contents(self, directory: Path, expected_names: set[str]) -> None:
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise DocumentStorageError("无法访问文档存储") from exc
        actual_names = {child.name for child in children}
        if actual_names != expected_names:
            raise DocumentStorageError("文档存储包含未登记文件")
        for child in children:
            self._assert_controlled_file(child, directory)

    def _delete_recoverable_file(self, path: Path, directory: Path) -> None:
        self._assert_controlled_file(path, directory)
        try:
            path.unlink()
        except OSError as exc:
            raise DocumentStorageError("无法恢复文档存储") from exc

    @staticmethod
    def _is_server_raw_name(name: str) -> bool:
        match = _SERVER_RAW_NAME.fullmatch(name)
        if match is None:
            return False
        return (
            str(UUID(match.group("document_id"))) == match.group("document_id")
            and match.group("suffix") in _ALLOWED_MEDIA_TYPES
        )

    @staticmethod
    def _is_server_text_name(name: str) -> bool:
        match = _SERVER_TEXT_NAME.fullmatch(name)
        return match is not None and str(UUID(name.removesuffix(".txt"))) == name.removesuffix(".txt")

    @staticmethod
    def _is_temporary_name(name: str) -> bool:
        return _TEMPORARY_NAME.fullmatch(name) is not None or _LEGACY_TEMPORARY_NAME.fullmatch(name) is not None

    def _atomic_write_bytes(self, target: Path, content: bytes) -> None:
        if target.parent not in {self._root, self._files_directory, self._text_directory}:
            raise DocumentStorageError("无法访问文档存储")
        if not isinstance(content, bytes):
            raise DocumentStorageError("无法写入文档存储")
        temporary = target.parent / f".iris-document-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            self._remove_new_file(temporary)
            raise DocumentStorageError("无法写入文档存储") from exc

    def _unlink_controlled(self, path: Path, directory: Path) -> None:
        self._assert_controlled_file(path, directory)
        try:
            path.unlink()
        except OSError as exc:
            raise DocumentStorageError("无法删除文档") from exc

    @staticmethod
    def _remove_new_file(path: Path) -> None:
        try:
            if path.exists() and not path.is_symlink():
                path.unlink()
        except OSError:
            pass

    def _require(self, document_id: str) -> DocumentRecord:
        try:
            if str(UUID(document_id)) != document_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise DocumentNotFoundError("文档不存在") from None
        document = self._records.get(document_id)
        if document is None:
            raise DocumentNotFoundError("文档不存在")
        return document

    @staticmethod
    def _validate_upload(original_name: str, content: bytes, media_type: str) -> tuple[str, str, str]:
        if not isinstance(original_name, str) or not isinstance(content, bytes) or not isinstance(media_type, str):
            raise DocumentInvalidTypeError("不支持该文档类型")
        safe_name = PureWindowsPath(original_name).name
        safe_name = PurePosixPath(safe_name).name.strip()
        if not safe_name or safe_name in {".", ".."} or not content:
            raise DocumentInvalidTypeError("不支持该文档类型")
        suffix = PurePosixPath(safe_name).suffix.lower()
        normalized_media_type = media_type.strip().lower()
        if suffix not in _ALLOWED_MEDIA_TYPES or normalized_media_type not in _ALLOWED_MEDIA_TYPES[suffix]:
            raise DocumentInvalidTypeError("不支持该文档类型")
        return safe_name, suffix, normalized_media_type

    @staticmethod
    def _safe_failure_message(message: str | None) -> str:
        if message is None:
            return "无法提取文档文本"
        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > 200
            or "\r" in message
            or "\n" in message
        ):
            raise DocumentValidationError("文档提取错误信息无效")
        return message.strip()
