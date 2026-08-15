"""Safe, minimal memory ledger model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

_CATEGORIES = frozenset({"preference", "fact", "project", "other"})
_PERSISTED_FIELDS = frozenset(
    {"id", "content", "category", "created_at", "updated_at", "source_session_id"}
)
_MAX_CONTENT_CHARS = 500


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """The sole entry shape that may be written to the memory ledger."""

    id: str
    content: str
    category: str
    created_at: str
    updated_at: str
    source_session_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("invalid memory id")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("memory content must be non-blank")
        if len(self.content) > _MAX_CONTENT_CHARS:
            raise ValueError("memory content is too long")
        if self.category not in _CATEGORIES:
            raise ValueError("invalid memory category")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("invalid memory created_at")
        if not isinstance(self.updated_at, str) or not self.updated_at:
            raise ValueError("invalid memory updated_at")
        if self.source_session_id is not None and not isinstance(self.source_session_id, str):
            raise ValueError("invalid memory source session")

    @classmethod
    def new(
        cls,
        content: str,
        category: str,
        *,
        source_session_id: str | None = None,
        entry_id: str | None = None,
    ) -> "MemoryEntry":
        """Create an entry with a generated identifier and UTC timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=entry_id or f"memory_{uuid4().hex}",
            content=content,
            category=category,
            created_at=now,
            updated_at=now,
            source_session_id=source_session_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_session_id": self.source_session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        if not isinstance(data, dict) or set(data) != _PERSISTED_FIELDS:
            raise ValueError("invalid memory entry")
        return cls(
            id=data["id"],
            content=data["content"],
            category=data["category"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            source_session_id=data["source_session_id"],
        )
