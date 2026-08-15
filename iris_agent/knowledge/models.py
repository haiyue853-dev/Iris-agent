"""Knowledge base entry model: safe, whitelisted records for interview notes."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

_ID_PATTERN = re.compile(r"^kb-[0-9a-f]{12}$")
_SOURCE_TYPES = frozenset({"scrape", "manual"})
_PERSISTED_FIELDS = frozenset(
    {"id", "title", "content", "category", "source_url", "source_type", "created_at", "updated_at"}
)

_MAX_TITLE_CHARS = 200
_MAX_CONTENT_CHARS = 50000
_MAX_CATEGORY_CHARS = 50
_MAX_SOURCE_URL_CHARS = 2000


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """A single interview-note record persisted to the knowledge base."""

    id: str
    title: str
    content: str
    category: str
    source_url: str | None
    source_type: str
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise ValueError("invalid knowledge id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("knowledge title must be non-blank")
        if len(self.title) > _MAX_TITLE_CHARS:
            raise ValueError("knowledge title is too long")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("knowledge content must be non-blank")
        if len(self.content) > _MAX_CONTENT_CHARS:
            raise ValueError("knowledge content is too long")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("knowledge category must be non-blank")
        if len(self.category) > _MAX_CATEGORY_CHARS:
            raise ValueError("knowledge category is too long")
        if self.source_type not in _SOURCE_TYPES:
            raise ValueError("invalid knowledge source type")
        if self.source_url is not None and (
            not isinstance(self.source_url, str) or len(self.source_url) > _MAX_SOURCE_URL_CHARS
        ):
            raise ValueError("invalid knowledge source url")
        if not isinstance(self.created_at, (int, float)) or not isinstance(self.updated_at, (int, float)):
            raise ValueError("invalid knowledge timestamp")

    @classmethod
    def new(
        cls,
        title: str,
        content: str,
        *,
        category: str = "面经",
        source_url: str | None = None,
        source_type: str = "manual",
    ) -> "KnowledgeEntry":
        """Create an entry with a generated identifier and current timestamp."""
        now = time.time()
        return cls(
            id=f"kb-{uuid4().hex[:12]}",
            title=title,
            content=content,
            category=category,
            source_url=source_url,
            source_type=source_type,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEntry":
        if not isinstance(data, dict) or set(data) != _PERSISTED_FIELDS:
            raise ValueError("invalid knowledge entry")
        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            category=data["category"],
            source_url=data["source_url"],
            source_type=data["source_type"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
