from __future__ import annotations

import json
import os
from pathlib import Path
import hashlib
import random
import tempfile
import time
from typing import Any


REVIEW_STATES = {"new", "known", "learning", "review"}
REVIEW_INTERVALS = {"known": 7 * 24 * 60 * 60, "learning": 4 * 60 * 60, "review": 24 * 60 * 60, "new": 0}


class InterviewKnowledgeRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self, topic: str | None = None) -> list[dict[str, Any]]:
        items = self._read()
        if topic:
            target = topic.strip().casefold()
            items = [item for item in items if str(item.get("topic", "")).casefold() == target]
        return sorted((self._item_data(item) for item in items), key=lambda item: float(item.get("saved_at", 0)), reverse=True)

    def next_review(self, topic: str | None = None, now: float | None = None) -> dict[str, Any] | None:
        now = time.time() if now is None else now
        items = self.list(topic)
        if not items:
            return None
        due = [item for item in items if float(item["next_review_at"]) <= now]
        if not due:
            return None
        candidates = due
        state_priority = {"learning": 0, "review": 1, "new": 2, "known": 3}
        best_priority = min(state_priority.get(str(item["review_state"]), 4) for item in candidates)
        preferred = [item for item in candidates if state_priority.get(str(item["review_state"]), 4) == best_priority]
        return random.choice(preferred)

    def mark_reviewed(self, item_id: str, review_state: str, now: float | None = None) -> dict[str, Any]:
        if review_state not in REVIEW_STATES:
            raise ValueError("review state must be one of: known, learning, review")
        now = time.time() if now is None else now
        items = self._read()
        for item in items:
            if self._item_id(item) != item_id:
                continue
            item["review_state"] = review_state
            item["reviewed_at"] = now
            item["next_review_at"] = now + REVIEW_INTERVALS[review_state]
            self._write(items)
            return self._item_data(item)
        raise KeyError(item_id)

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
            existing.append({
                "id": self._id_for(topic, question), "topic": topic, "question": question, "answer": answer,
                "source_url": source_url, "saved_at": time.time(), "review_state": "new", "reviewed_at": None,
                "next_review_at": 0,
            })
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

    def _item_data(self, item: dict[str, Any]) -> dict[str, Any]:
        state = str(item.get("review_state", "new"))
        if state not in REVIEW_STATES:
            state = "new"
        return {
            **item,
            "id": self._item_id(item),
            "review_state": state,
            "reviewed_at": item.get("reviewed_at"),
            "next_review_at": float(item.get("next_review_at", 0)),
        }

    def _item_id(self, item: dict[str, Any]) -> str:
        return str(item.get("id") or self._id_for(str(item.get("topic", "")), str(item.get("question", ""))))

    @staticmethod
    def _id_for(topic: str, question: str) -> str:
        key = f"{topic.strip().casefold()}\n{question.strip().casefold()}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()[:16]

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
