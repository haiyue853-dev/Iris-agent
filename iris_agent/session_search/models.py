"""Search hit model: a matched session fragment with a relevance score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_PUBLIC_FIELDS = ("session_id", "session_name", "role", "content", "updated_at", "score")


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single matched user/assistant message fragment."""

    session_id: str
    session_name: str
    role: str
    content: str
    updated_at: float
    score: int

    def to_dict(self, max_chars: int = 300) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "role": self.role,
            "content": self.content[:max_chars],
            "updated_at": self.updated_at,
            "score": self.score,
        }
