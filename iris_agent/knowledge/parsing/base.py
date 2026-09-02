"""Domain models and the parser protocol for knowledge document parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

_SECTION_KINDS = frozenset({"text", "table", "image"})


class ParsingError(ValueError):
    """A knowledge source file could not be parsed into text sections."""


@dataclass(frozen=True, slots=True)
class ParsedSection:
    """One homogeneous block extracted from a source document."""

    text: str
    kind: str = "text"
    location: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("parsed section text must be a string")
        if self.kind not in _SECTION_KINDS:
            raise ValueError("invalid parsed section kind")
        if self.location is not None and not isinstance(self.location, str):
            raise ValueError("invalid parsed section location")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """The full text extraction of one source file, ordered by document position."""

    sections: tuple[ParsedSection, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.sections, tuple) or not all(isinstance(item, ParsedSection) for item in self.sections):
            raise ValueError("parsed document sections must be a tuple of ParsedSection")
        if not isinstance(self.warnings, tuple) or not all(isinstance(item, str) for item in self.warnings):
            raise ValueError("parsed document warnings must be a tuple of strings")

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections if section.text.strip())

    @property
    def locations(self) -> tuple[str, ...]:
        return tuple(section.location for section in self.sections if section.location)


class DocumentParser(Protocol):
    def parse(self, content: bytes, *, name: str) -> tuple[ParsedSection, ...]: ...
