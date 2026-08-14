from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import tempfile
import time

from iris_agent.core.models import Message


@dataclass(slots=True)
class ContextSnapshot:
    session_id: str
    through_message_id: str
    summary: str
    created_at: float


class JsonContextSnapshotRepository:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str, through_message_id: str) -> ContextSnapshot | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            snapshot = ContextSnapshot(**value)
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        return snapshot if snapshot.through_message_id == through_message_id else None

    def save(self, snapshot: ContextSnapshot) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, delete=False, suffix=".tmp") as handle:
                temporary = Path(handle.name)
                json.dump(asdict(snapshot), handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(snapshot.session_id))
        except OSError:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.directory / f"{hashlib.sha256(session_id.encode()).hexdigest()}.json"


class ContextEngine:
    def __init__(self, snapshots: JsonContextSnapshotRepository, max_chars: int = 80_000) -> None:
        self.snapshots = snapshots
        self.max_chars = max_chars

    def build(self, session_id: str, system_prompt: str, history: list[Message]) -> list[Message]:
        if len(system_prompt) + sum(len(message.content) for message in history) <= self.max_chars:
            return [Message(role="system", content=system_prompt), *history]
        tail = self._recent_tail(history)
        older = history[:len(history) - len(tail)]
        if not older:
            return [Message(role="system", content=system_prompt), *tail]
        snapshot = self.snapshots.get(session_id, older[-1].id)
        summary = snapshot.summary if snapshot else self._summarize(older)
        if not snapshot:
            self.snapshots.save(ContextSnapshot(session_id, older[-1].id, summary, time.time()))
        available = max(0, self.max_chars - len(system_prompt) - sum(len(message.content) for message in tail) - 40)
        summary = summary[:available]
        compressed_prompt = f"{system_prompt}\n\nConversation summary:\n{summary}" if summary else system_prompt
        return [Message(role="system", content=compressed_prompt), *tail]

    def _recent_tail(self, history: list[Message]) -> list[Message]:
        budget, used, tail = max(1_000, self.max_chars // 2), 0, []
        for message in reversed(history):
            size = len(message.content)
            if tail and used + size > budget:
                break
            tail.append(message)
            used += size
        return list(reversed(tail))

    @staticmethod
    def _summarize(messages: list[Message]) -> str:
        lines = []
        for message in messages:
            content = " ".join(message.content.split())[:280]
            if message.role == "tool" and message.name:
                content = f"{message.name}: {content}"
            lines.append(f"- {message.role}: {content}")
        return "\n".join(lines)
