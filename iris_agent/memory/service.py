"""Memory service: add, list, delete, and select entries for injection."""

from __future__ import annotations

from iris_agent.memory.models import MemoryEntry
from iris_agent.memory.repository import MemoryRepository


class MemoryNotFoundError(RuntimeError):
    """The requested memory entry does not exist."""


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        max_entries: int = 500,
        max_chars: int = 500,
        max_injected_chars: int = 2000,
        max_injected_entries: int = 20,
    ):
        self.repository = repository
        self.max_entries = max_entries
        self.max_chars = max_chars
        self.max_injected_chars = max_injected_chars
        self.max_injected_entries = max_injected_entries

    def add(self, content: str, category: str, source_session_id: str | None = None) -> MemoryEntry:
        if not isinstance(content, str) or len(content) > self.max_chars:
            raise ValueError("memory content is invalid")
        with self.repository.lock:
            entry = MemoryEntry.new(content, category, source_session_id=source_session_id)
            entries = self.repository.load()
            entries.append(entry)
            self._save_bounded(entries)
            return entry

    def list(self) -> list[MemoryEntry]:
        entries = self.repository.load()
        return sorted(entries, key=lambda item: item.updated_at, reverse=True)

    def delete(self, entry_id: str) -> None:
        with self.repository.lock:
            entries = self.repository.load()
            remaining = [item for item in entries if item.id != entry_id]
            if len(remaining) == len(entries):
                raise MemoryNotFoundError(entry_id)
            self.repository.save(remaining)

    def inject(self) -> list[MemoryEntry]:
        selected: list[MemoryEntry] = []
        total_chars = 0
        for entry in self.list():
            if len(selected) >= self.max_injected_entries:
                break
            if total_chars + len(entry.content) > self.max_injected_chars:
                continue
            selected.append(entry)
            total_chars += len(entry.content)
        return selected

    def _save_bounded(self, entries: list[MemoryEntry]) -> None:
        if len(entries) > self.max_entries:
            entries = entries[len(entries) - self.max_entries :]
        self.repository.save(entries)
