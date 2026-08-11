"""文档工作台的无正文元数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Callable, Literal
from uuid import UUID


DocumentExtractionStatus = Literal["pending", "ready", "failed"]
DocumentTemplate = Literal["meeting_minutes", "prd", "technical_solution", "weekly_report"]
DOCUMENT_TEMPLATES = frozenset({"meeting_minutes", "prd", "technical_solution", "weekly_report"})


def _is_basename(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and PureWindowsPath(value).name == value
        and PurePosixPath(value).name == value
        and value not in {".", ".."}
    )


@dataclass(frozen=True, slots=True)
class DocumentSource:
    file_name: str
    location: str | None = None

    def __post_init__(self) -> None:
        if not _is_basename(self.file_name):
            raise ValueError("document source file name must be a basename")
        if self.location is not None and (
            not isinstance(self.location, str)
            or not self.location.strip()
            or len(self.location) > 200
            or "\r" in self.location
            or "\n" in self.location
        ):
            raise ValueError("document source location is invalid")


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    text: str
    sources: tuple[DocumentSource, ...]
    truncated: bool

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("document extraction text is invalid")
        if not isinstance(self.sources, tuple) or not self.sources or not all(
            isinstance(source, DocumentSource) for source in self.sources
        ):
            raise ValueError("document extraction sources are invalid")
        if not isinstance(self.truncated, bool):
            raise ValueError("document extraction truncation is invalid")


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """可返回给客户端的文档元数据；正文单独存放在 ``text/``。"""

    id: str
    original_name: str
    suffix: str
    media_type: str
    size_bytes: int
    created_at: float
    extraction_status: DocumentExtractionStatus = "pending"
    extraction_message: str | None = None
    text_truncated: bool = False
    sources: tuple[DocumentSource, ...] = ()

    def __post_init__(self) -> None:
        try:
            if str(UUID(self.id)) != self.id:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("document id must be a canonical UUID") from exc
        if not _is_basename(self.original_name):
            raise ValueError("document name must be a basename")
        if (
            not isinstance(self.suffix, str)
            or not self.suffix.startswith(".")
            or self.suffix != self.suffix.lower()
            or PurePosixPath(self.original_name).suffix.lower() != self.suffix
            or not isinstance(self.media_type, str)
            or not self.media_type.strip()
            or not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 1
            or not isinstance(self.created_at, (int, float))
            or isinstance(self.created_at, bool)
            or not math.isfinite(self.created_at)
        ):
            raise ValueError("document metadata is invalid")
        if self.extraction_status not in {"pending", "ready", "failed"}:
            raise ValueError("document extraction status is invalid")
        if not isinstance(self.text_truncated, bool):
            raise ValueError("document truncation is invalid")
        if not isinstance(self.sources, tuple) or not all(
            isinstance(source, DocumentSource) for source in self.sources
        ):
            raise ValueError("document sources are invalid")
        if self.extraction_message is not None and (
            not isinstance(self.extraction_message, str)
            or not self.extraction_message.strip()
            or len(self.extraction_message) > 200
            or "\r" in self.extraction_message
            or "\n" in self.extraction_message
        ):
            raise ValueError("document extraction message is invalid")
        if self.extraction_status == "ready":
            if self.extraction_message is not None or not self.sources:
                raise ValueError("ready document extraction is invalid")
        elif self.sources or self.text_truncated:
            raise ValueError("unfinished document extraction is invalid")
        elif self.extraction_status == "pending" and self.extraction_message is not None:
            raise ValueError("pending document extraction is invalid")
        elif self.extraction_status == "failed" and self.extraction_message is None:
            raise ValueError("failed document extraction is invalid")


class DocumentFile:
    """不暴露服务器路径的受控原文读取句柄。"""

    def __init__(self, name: str, suffix: str, reader: Callable[[], bytes]):
        self._name = name
        self._suffix = suffix
        self._reader = reader

    @property
    def name(self) -> str:
        return self._name

    @property
    def suffix(self) -> str:
        return self._suffix

    def read_bytes(self) -> bytes:
        return self._reader()


def _is_canonical_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


@dataclass(frozen=True, slots=True)
class DocumentCitation:
    document_id: str
    location: str

    def __post_init__(self) -> None:
        if not _is_canonical_uuid(self.document_id):
            raise ValueError("document citation id is invalid")
        if (
            not isinstance(self.location, str)
            or not self.location.strip()
            or self.location != self.location.strip()
            or len(self.location) > 200
            or "\r" in self.location
            or "\n" in self.location
        ):
            raise ValueError("document citation location is invalid")


@dataclass(frozen=True, slots=True)
class DocumentDraft:
    id: str
    title: str
    template: DocumentTemplate
    document_ids: tuple[str, ...]
    instructions: str
    markdown: str
    citations: tuple[DocumentCitation, ...]
    revision: int
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        if not _is_canonical_uuid(self.id):
            raise ValueError("document draft id is invalid")
        if (
            not isinstance(self.title, str)
            or not self.title.strip()
            or self.title != self.title.strip()
            or len(self.title) > 200
            or "\r" in self.title
            or "\n" in self.title
        ):
            raise ValueError("document draft title is invalid")
        if self.template not in DOCUMENT_TEMPLATES:
            raise ValueError("document draft template is invalid")
        if (
            not isinstance(self.document_ids, tuple)
            or not self.document_ids
            or len(self.document_ids) != len(set(self.document_ids))
            or not all(_is_canonical_uuid(item) for item in self.document_ids)
        ):
            raise ValueError("document draft sources are invalid")
        if not isinstance(self.instructions, str) or len(self.instructions) > 2_000:
            raise ValueError("document draft instructions are invalid")
        if (
            not isinstance(self.markdown, str)
            or not self.markdown.strip()
            or self.markdown != self.markdown.strip()
        ):
            raise ValueError("document draft markdown is invalid")
        if (
            not isinstance(self.citations, tuple)
            or not all(isinstance(item, DocumentCitation) for item in self.citations)
            or any(item.document_id not in self.document_ids for item in self.citations)
        ):
            raise ValueError("document draft citations are invalid")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("document draft revision is invalid")
        if any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            for value in (self.created_at, self.updated_at)
        ):
            raise ValueError("document draft timestamps are invalid")
