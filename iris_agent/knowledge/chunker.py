"""Chinese-aware, lossless text chunking for local-RAG ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    content: str
    location: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("chunk draft content must be non-blank")


@dataclass(frozen=True, slots=True)
class ChunkGroup:
    """A parent context block with the smaller child chunks indexed for retrieval."""

    parent: ChunkDraft
    children: tuple[ChunkDraft, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.parent, ChunkDraft):
            raise ValueError("chunk group parent must be a ChunkDraft")
        if not isinstance(self.children, tuple) or not all(isinstance(item, ChunkDraft) for item in self.children):
            raise ValueError("chunk group children must be a tuple of ChunkDraft")


def build_chunks(
    text: str,
    *,
    location: str | None,
    target_chars: int,
    overlap_chars: int,
    parent_target_chars: int | None = None,
    child_target_chars: int | None = None,
    child_overlap_chars: int | None = None,
) -> list[ChunkDraft | ChunkGroup]:
    """Build flat chunks, or parent-child groups when parent_target_chars is set."""
    if parent_target_chars is None:
        return chunk_text(text, location=location, target_chars=target_chars, overlap_chars=overlap_chars)
    child_target = child_target_chars or min(target_chars, parent_target_chars)
    child_overlap = child_overlap_chars or 0
    groups = parent_child_chunks(
        text,
        location=location,
        parent_target_chars=parent_target_chars,
        child_target_chars=child_target,
        child_overlap_chars=child_overlap,
    )
    return list(groups)


def parent_child_chunks(
    text: str,
    *,
    location: str | None,
    parent_target_chars: int,
    child_target_chars: int,
    child_overlap_chars: int,
) -> list[ChunkGroup]:
    """Split at heading/paragraph boundaries into parents, then index-sized children."""
    if isinstance(parent_target_chars, bool) or not isinstance(parent_target_chars, int) or parent_target_chars < 1:
        raise ValueError("parent_target_chars must be positive")
    if isinstance(child_target_chars, bool) or not isinstance(child_target_chars, int) or child_target_chars < 1:
        raise ValueError("child_target_chars must be positive")
    if child_target_chars > parent_target_chars:
        raise ValueError("child_target_chars must not exceed parent_target_chars")
    if isinstance(child_overlap_chars, bool) or not isinstance(child_overlap_chars, int) or not 0 <= child_overlap_chars < child_target_chars:
        raise ValueError("child_overlap_chars must be non-negative and smaller than child_target_chars")
    if not isinstance(text, str) or not text.strip():
        return []
    groups: list[ChunkGroup] = []
    for parent in chunk_text(text, location=location, target_chars=parent_target_chars, overlap_chars=0):
        children = tuple(
            chunk_text(parent.content, location=parent.location, target_chars=child_target_chars, overlap_chars=child_overlap_chars)
        )
        if len(children) == 1 and children[0].content == parent.content:
            children = ()
        groups.append(ChunkGroup(parent=parent, children=children))
    return groups


def _units(text: str) -> list[str]:
    """Keep paragraph and common Chinese sentence boundaries in their units."""
    return [unit for unit in re.findall(r".+?(?:\n\s*\n|[。！？!?]+|$)", text, flags=re.DOTALL) if unit]


def chunk_text(
    text: str, *, location: str | None, target_chars: int, overlap_chars: int, _semantic: bool = True
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

    if _semantic:
        sections: list[tuple[str | None, str]] = []
        stack: list[str] = []
        buffer: list[str] = []
        found = False
        for line in text.splitlines(keepends=True):
            markdown = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line.rstrip("\r\n"))
            numbered = re.match(r"^\s*((?:第[一二三四五六七八九十百\d]+[章节]|\d+(?:\.\d+){0,4}[、.、]?)\s*.+?)\s*$", line.rstrip("\r\n"))
            if markdown or numbered:
                if buffer:
                    sections.append((" → ".join(stack) or None, "".join(buffer)))
                found = True
                if markdown:
                    level, label = len(markdown.group(1)), markdown.group(2)
                    stack = stack[:level - 1] + [label]
                else:
                    stack = [numbered.group(1)]
                buffer = [line]
            else:
                buffer.append(line)
        if buffer:
            sections.append((" → ".join(stack) or None, "".join(buffer)))
        if found:
            drafts: list[ChunkDraft] = []
            for heading, section in sections:
                section_location = " · ".join(part for part in (location, heading) if part)
                drafts.extend(chunk_text(section, location=section_location or None, target_chars=target_chars, overlap_chars=overlap_chars, _semantic=False))
            return drafts

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
            capacity = target_chars - len(remainder)
            carry = overlap[-min(len(overlap), capacity):] if overlap and capacity > 0 else ""
            current = carry + remainder
            break
    if current:
        completed.append(current)
    draft_contents: list[str] = []
    pending_whitespace = ""
    for content in completed:
        if content.strip():
            if draft_contents and pending_whitespace:
                capacity = target_chars - len(content)
                content = (pending_whitespace[-capacity:] if capacity > 0 else "") + content
            pending_whitespace = ""
            draft_contents.append(content)
        else:
            pending_whitespace += content
    return [ChunkDraft(content=content, location=location) for content in draft_contents]
