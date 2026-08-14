"""Safe, minimal task-queue ledger model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


QueueState = Literal["queued", "active"]
_PERSISTED_FIELDS = frozenset({"task_id", "session_id", "message", "created_at", "state"})


@dataclass(frozen=True, slots=True)
class QueueJob:
    """The sole job shape that may be written to the queue ledger."""

    task_id: str
    session_id: str
    message: str
    created_at: str
    state: QueueState

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (self.task_id, self.session_id, self.message, self.created_at)):
            raise ValueError("invalid queue job")
        if self.state not in {"queued", "active"}:
            raise ValueError("invalid queue job state")

    @classmethod
    def new(cls, session_id: str, message: str, *, task_id: str | None = None) -> "QueueJob":
        """Create a queued job with a generated identifier and UTC timestamp."""
        return cls(
            task_id=task_id or str(uuid4()),
            session_id=session_id,
            message=message,
            created_at=datetime.now(timezone.utc).isoformat(),
            state="queued",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "message": self.message,
            "created_at": self.created_at,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueJob":
        if not isinstance(data, dict) or set(data) != _PERSISTED_FIELDS:
            raise ValueError("invalid queue job")
        if not all(isinstance(data[key], str) for key in _PERSISTED_FIELDS):
            raise ValueError("invalid queue job")
        return cls(
            task_id=data["task_id"],
            session_id=data["session_id"],
            message=data["message"],
            created_at=data["created_at"],
            state=data["state"],
        )
