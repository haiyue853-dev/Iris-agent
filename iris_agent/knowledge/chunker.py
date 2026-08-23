"""Chinese-aware, lossless text chunking for local-RAG ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    content: str
    location: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("chunk draft content must be non-empty")


def _units(text: str) -> list[str]:
    """Keep paragraph and common Chinese sentence boundaries in their units."""
    return [unit for unit in re.findall(r".+?(?:\n\s*\n|[。！？!?]+|$)", text, flags=re.DOTALL) if unit]


def chunk_text(
    text: str, *, location: str | None, target_chars: int, overlap_chars: int
) -> list[ChunkDraft]:
    """Chunk text at preferred Chinese boundaries without dropping source characters."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if isinstance(target_chars, bool) or not isinstance(target_chars, int) or target_chars < 1:
        raise ValueError("target_chars must be positive")
    if isinstance(overlap_chars, bool) or not isinstance(overlap_chars, int) or not 0 <= overlap_chars < target_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than target_chars")
    if not text.strip():
        return []

    completed: list[str] = []
    current = ""
    for unit in _units(text):
        remainder = unit
        while remainder:
            if len(current) + len(remainder) <= target_chars:
                current += remainder
                break
            if current:
                completed.append(current)
            overlap = current[-overlap_chars:] if overlap_chars else ""
            while len(remainder) > target_chars:
                available = target_chars - len(overlap)
                chunk = overlap + remainder[:available]
                completed.append(chunk)
                remainder = remainder[available:]
                overlap = chunk[-overlap_chars:] if overlap_chars else ""
            carry = overlap[-min(len(overlap), target_chars - len(remainder)):] if overlap else ""
            current = carry + remainder
            break
    if current:
        completed.append(current)
    return [ChunkDraft(content=content, location=location) for content in completed]
