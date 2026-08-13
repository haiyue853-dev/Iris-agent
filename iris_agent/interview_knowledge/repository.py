from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


class InterviewKnowledgeRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self, topic: str | None = None) -> list[dict[str, Any]]:
        items = self._read()
        if topic:
            target = topic.strip().casefold()
            items = [item for item in items if str(item.get("topic", "")).casefold() == target]
        return sorted(items, key=lambda item: float(item.get("saved_at", 0)), reverse=True)

    def save(self, topic: str, items: list[dict[str, object]]) -> dict[str, int]:
        topic = topic.strip()
        if not topic or not items:
            raise ValueError("topic and question-answer pairs are required")
        existing = self._read()
        known = {(str(item.get("topic", "")).casefold(), str(item.get("question", "")).casefold()) for item in existing}
        added = 0
        for item in items:
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            source_url = str(item.get("source_url", "")).strip()
            key = (topic.casefold(), question.casefold())
            if not question or not answer or key in known:
                continue
            existing.append({"topic": topic, "question": question, "answer": answer, "source_url": source_url, "saved_at": time.time()})
            known.add(key)
            added += 1
        self._write(existing)
        return {"added": added, "total": len(existing)}

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("interview knowledge storage is unreadable") from exc
        if not isinstance(value, list):
            raise ValueError("interview knowledge storage is invalid")
        return [item for item in value if isinstance(item, dict)]

    def _write(self, items: list[dict[str, Any]]) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
                temporary = Path(handle.name)
                json.dump(items, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            if temporary: temporary.unlink(missing_ok=True)
            raise ValueError("interview knowledge storage cannot be saved") from exc
