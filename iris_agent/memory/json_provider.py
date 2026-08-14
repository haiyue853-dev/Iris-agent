from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
from uuid import uuid4

from iris_agent.memory.models import MemoryItem


class JsonMemoryProvider:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def remember(self, content: str, session_id: str | None = None, tags: tuple[str, ...] = ()) -> MemoryItem:
        content = content.strip()
        if not content:
            raise ValueError("memory content is required")
        session_id = session_id.strip() if session_id else None
        tags = tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        with self._lock:
            items = self._read()
            now = time.time()
            for index, item in enumerate(items):
                if item.content.casefold() == content.casefold() and item.session_id == session_id:
                    updated = MemoryItem(item.id, item.content, item.session_id, tags or item.tags, item.created_at, now)
                    items[index] = updated
                    self._write(items)
                    return updated
            item = MemoryItem(f"memory_{uuid4().hex}", content, session_id, tags, now, now)
            items.append(item)
            self._write(items)
            return item

    def search(self, query: str, session_id: str | None = None, limit: int = 4) -> list[MemoryItem]:
        tokens = [token.casefold() for token in query.split() if token.strip()]
        query_text = query.strip().casefold()
        with self._lock:
            candidates = [item for item in self._read() if item.session_id in {None, session_id}]
        def score(item: MemoryItem) -> tuple[int, float]:
            text = f"{item.content} {' '.join(item.tags)}".casefold()
            matched = int(bool(query_text and query_text in text)) * 10 + sum(token in text for token in tokens)
            return matched, item.updated_at
        return [item for item in sorted(candidates, key=score, reverse=True) if score(item)[0]][:max(1, min(limit, 10))]

    def list(self, session_id: str | None = None) -> list[MemoryItem]:
        with self._lock:
            items = self._read()
        if session_id is not None:
            items = [item for item in items if item.session_id == session_id]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def delete(self, memory_id: str) -> None:
        with self._lock:
            items = self._read()
            remaining = [item for item in items if item.id != memory_id]
            if len(remaining) == len(items):
                raise KeyError(memory_id)
            self._write(remaining)

    def _read(self) -> list[MemoryItem]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("memory storage is unreadable") from exc
        if not isinstance(value, list):
            raise ValueError("memory storage is invalid")
        return [MemoryItem(str(item["id"]), str(item["content"]), item.get("session_id"), tuple(item.get("tags", [])), float(item["created_at"]), float(item["updated_at"])) for item in value if isinstance(item, dict)]

    def _write(self, items: list[MemoryItem]) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
                temporary = Path(handle.name)
                json.dump([{
                    "id": item.id, "content": item.content, "session_id": item.session_id, "tags": list(item.tags),
                    "created_at": item.created_at, "updated_at": item.updated_at,
                } for item in items], handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            if temporary:
                temporary.unlink(missing_ok=True)
            raise ValueError("memory storage cannot be saved") from exc
