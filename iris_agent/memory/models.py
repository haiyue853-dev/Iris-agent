from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    content: str
    session_id: str | None
    tags: tuple[str, ...]
    created_at: float
    updated_at: float
