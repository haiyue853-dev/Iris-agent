"""Task-center domain models with an intentionally narrow persisted shape."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """A safe timeline entry; it deliberately has no arbitrary payload field."""

    id: str
    type: str
    label: str
    created_at: str
    tool_name: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "created_at": self.created_at,
        }
        if self.tool_name is not None:
            data["tool_name"] = self.tool_name
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEvent":
        required = ("id", "type", "label", "created_at")
        if not all(isinstance(data.get(key), str) for key in required):
            raise ValueError("invalid task event")
        if data.get("tool_name") is not None and not isinstance(data["tool_name"], str):
            raise ValueError("invalid task event")
        if data.get("duration_ms") is not None and (
            isinstance(data["duration_ms"], bool) or not isinstance(data["duration_ms"], int)
        ):
            raise ValueError("invalid task event")
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            created_at=data["created_at"],
            tool_name=data.get("tool_name"),
            duration_ms=data.get("duration_ms"),
        )


@dataclass(frozen=True, slots=True)
class AgentTask:
    id: str
    session_id: str
    request_summary: str
    status: str
    created_at: str
    updated_at: str
    finished_at: str | None = None
    events: tuple[TaskEvent, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "session_id": self.session_id,
            "request_summary": self.request_summary,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": [event.to_dict() for event in self.events],
        }
        if self.finished_at is not None:
            data["finished_at"] = self.finished_at
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        raw_events = data.get("events", [])
        if not isinstance(raw_events, list) or not all(isinstance(item, dict) for item in raw_events):
            raise ValueError("invalid task events")
        return cls(
            id=str(data["id"]),
            session_id=str(data["session_id"]),
            request_summary=str(data["request_summary"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            finished_at=str(data["finished_at"]) if data.get("finished_at") is not None else None,
            events=tuple(TaskEvent.from_dict(item) for item in raw_events),
        )

    def without_events(self) -> "AgentTask":
        return replace(self, events=())
