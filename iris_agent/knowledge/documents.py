"""Domain models for persisted local-RAG documents and chunks."""

from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

_DOCUMENT_ID = re.compile(r"^doc-[0-9a-f]{32}$")
_CHUNK_ID = re.compile(r"^chunk-[0-9a-f]{32}$")
_DOCUMENT_STATUSES = frozenset({"queued", "indexing", "ready", "failed"})
_SOURCE_TYPES = frozenset({"upload", "manual", "scrape"})
_DOCUMENT_FIELDS = frozenset({
    "id", "title", "source_type", "media_type", "size_bytes", "original_name", "status",
    "error_message", "created_at", "updated_at",
})
_CHUNK_FIELDS = frozenset({"id", "document_id", "ordinal", "content", "location", "content_hash", "parent_id"})


def _is_timestamp(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    title: str
    source_type: str
    media_type: str | None
    size_bytes: int
    original_name: str | None
    status: str
    error_message: str | None
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _DOCUMENT_ID.fullmatch(self.id):
            raise ValueError("invalid knowledge document id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("knowledge document title must be non-blank")
        if self.source_type not in _SOURCE_TYPES:
            raise ValueError("invalid knowledge document source type")
        if self.media_type is not None and (not isinstance(self.media_type, str) or not self.media_type.strip()):
            raise ValueError("invalid knowledge document media type")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("knowledge document size must be non-negative")
        if self.original_name is not None and (not isinstance(self.original_name, str) or not self.original_name.strip()):
            raise ValueError("invalid knowledge document original name")
        if self.status not in _DOCUMENT_STATUSES:
            raise ValueError("invalid knowledge document status")
        if self.error_message is not None and not isinstance(self.error_message, str):
            raise ValueError("invalid knowledge document error message")
        if not _is_timestamp(self.created_at) or not _is_timestamp(self.updated_at):
            raise ValueError("invalid knowledge document timestamp")

    @classmethod
    def new(
        cls,
        title: str,
        *,
        source_type: str,
        media_type: str | None = None,
        size_bytes: int = 0,
        original_name: str | None = None,
        status: str = "queued",
        error_message: str | None = None,
    ) -> "KnowledgeDocument":
        now = time.time()
        return cls(
            id=f"doc-{uuid4().hex}", title=title, source_type=source_type, media_type=media_type,
            size_bytes=size_bytes, original_name=original_name, status=status, error_message=error_message,
            created_at=now, updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _DOCUMENT_FIELDS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeDocument":
        if not isinstance(data, dict) or set(data) != _DOCUMENT_FIELDS:
            raise ValueError("invalid knowledge document")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: str
    document_id: str
    ordinal: int
    content: str
    location: str | None
    content_hash: str
    parent_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _CHUNK_ID.fullmatch(self.id):
            raise ValueError("invalid knowledge chunk id")
        if not isinstance(self.document_id, str) or not _DOCUMENT_ID.fullmatch(self.document_id):
            raise ValueError("invalid knowledge chunk document id")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ValueError("knowledge chunk ordinal must be non-negative")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("knowledge chunk content must be non-blank")
        if self.location is not None and not isinstance(self.location, str):
            raise ValueError("invalid knowledge chunk location")
        if not isinstance(self.content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("invalid knowledge chunk content hash")
        if self.parent_id is not None and (not isinstance(self.parent_id, str) or not _CHUNK_ID.fullmatch(self.parent_id)):
            raise ValueError("invalid knowledge chunk parent id")
        expected_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash != expected_hash:
            raise ValueError("knowledge chunk content hash does not match content")

    @classmethod
    def new(
        cls, document_id: str, ordinal: int, content: str, *, location: str | None = None, parent_id: str | None = None
    ) -> "KnowledgeChunk":
        return cls(
            id=f"chunk-{uuid4().hex}", document_id=document_id, ordinal=ordinal, content=content,
            location=location, content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(), parent_id=parent_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _CHUNK_FIELDS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeChunk":
        if not isinstance(data, dict) or set(data) != _CHUNK_FIELDS:
            raise ValueError("invalid knowledge chunk")
        return cls(**data)
