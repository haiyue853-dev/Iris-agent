from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _sources(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("sources must be a sequence of non-empty strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    id: str
    scope_id: str
    original_name: str
    media_type: str
    size_bytes: int
    created_at: datetime
    extraction_status: str
    extracted_text: str | None = None
    extraction_message: str | None = None
    text_truncated: bool = False
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("id", "scope_id", "original_name", "media_type", "extraction_status"):
            _non_empty(getattr(self, field), field)
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
        if self.extraction_message is not None and not isinstance(self.extraction_message, str):
            raise ValueError("extraction_message must be a string or None")
        if self.extracted_text is not None and not isinstance(self.extracted_text, str):
            raise ValueError("extracted_text must be a string or None")
        if not isinstance(self.text_truncated, bool):
            raise ValueError("text_truncated must be a boolean")
        object.__setattr__(self, "sources", _sources(self.sources))


@dataclass(frozen=True, slots=True)
class AttachmentReference:
    id: str
    original_name: str
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.id, "id")
        _non_empty(self.original_name, "original_name")
        object.__setattr__(self, "sources", _sources(self.sources))

    def to_dict(self) -> dict[str, str | list[str]]:
        return {"id": self.id, "original_name": self.original_name, "sources": list(self.sources)}

    @classmethod
    def from_dict(cls, payload: Any) -> "AttachmentReference":
        if not isinstance(payload, dict):
            raise ValueError("attachment reference must be an object")
        sources = payload.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("attachment reference sources must be a JSON array")
        try:
            return cls(id=payload["id"], original_name=payload["original_name"], sources=sources)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid attachment reference") from exc
