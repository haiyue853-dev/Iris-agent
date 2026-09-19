"""Small, serialisable models for the personal assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


TaskCertainty = Literal["create", "confirm"]
TaskTimeKind = Literal["exact", "vague", "none"]
TaskStatus = Literal["active", "completed", "cancelled"]


def _datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("task datetimes must include a timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class TaskDraft:
    title: str
    certainty: TaskCertainty = "create"
    time_kind: TaskTimeKind = "none"
    due_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("task title must not be blank")
        if self.certainty not in {"create", "confirm"}:
            raise ValueError("invalid task certainty")
        if self.time_kind not in {"exact", "vague", "none"}:
            raise ValueError("invalid task time kind")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("task due_at must include a timezone")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "certainty": self.certainty,
            "time_kind": self.time_kind,
            "due_at": self.due_at.isoformat() if self.due_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "TaskDraft":
        return cls(
            title=str(value["title"]),
            certainty=str(value.get("certainty", "create")),
            time_kind=str(value.get("time_kind", "none")),
            due_at=_datetime(value.get("due_at")),
        )


@dataclass(frozen=True, slots=True)
class MessageClassification:
    archive: bool = False
    title: str = ""
    summary: str = ""
    category: str = "其他"
    tags: tuple[str, ...] = ()
    task: TaskDraft | None = None


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    id: str
    title: str
    summary: str
    category: str
    tags: tuple[str, ...]
    source_message_id: str
    source_user_id: str
    created_at: datetime
    path: str
    original_text: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "tags": list(self.tags),
            "source_message_id": self.source_message_id,
            "source_user_id": self.source_user_id,
            "created_at": self.created_at.isoformat(),
            "path": self.path,
            "original_text": self.original_text,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ArchiveRecord":
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            summary=str(value.get("summary", "")),
            category=str(value.get("category", "其他")),
            tags=tuple(str(item) for item in value.get("tags", [])),
            source_message_id=str(value.get("source_message_id", "")),
            source_user_id=str(value.get("source_user_id", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            path=str(value["path"]),
            original_text=str(value.get("original_text", "")),
        )


@dataclass(frozen=True, slots=True)
class PersonalTask:
    short_id: str
    title: str
    user_id: str
    platform: str
    source_message_id: str
    source_text: str
    time_kind: TaskTimeKind
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    due_at: datetime
    next_remind_at: datetime
    reminder_count: int = 0
    last_reminded_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "short_id": self.short_id,
            "title": self.title,
            "user_id": self.user_id,
            "platform": self.platform,
            "source_message_id": self.source_message_id,
            "source_text": self.source_text,
            "time_kind": self.time_kind,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "next_remind_at": self.next_remind_at.isoformat(),
            "reminder_count": self.reminder_count,
            "last_reminded_at": self.last_reminded_at.isoformat() if self.last_reminded_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PersonalTask":
        return cls(
            short_id=str(value["short_id"]),
            title=str(value["title"]),
            user_id=str(value["user_id"]),
            platform=str(value.get("platform", "qq")),
            source_message_id=str(value.get("source_message_id", "")),
            source_text=str(value.get("source_text", "")),
            time_kind=str(value.get("time_kind", "none")),
            status=str(value.get("status", "active")),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
            due_at=datetime.fromisoformat(str(value["due_at"])),
            next_remind_at=datetime.fromisoformat(str(value["next_remind_at"])),
            reminder_count=int(value.get("reminder_count", 0)),
            last_reminded_at=_datetime(value.get("last_reminded_at")),
        )


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    duplicate: bool = False
    receipt: str = ""
    reply_override: str | None = None
    archive_records: tuple[ArchiveRecord, ...] = field(default_factory=tuple)
    tasks: tuple[PersonalTask, ...] = field(default_factory=tuple)
