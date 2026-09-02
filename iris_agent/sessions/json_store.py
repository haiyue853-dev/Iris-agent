from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import tempfile
import re
import threading
from contextlib import contextmanager
import time
import uuid

from iris_agent.core.errors import SessionError, SessionNotFoundError
from iris_agent.core.models import Message, ToolCall
from iris_agent.core.runtime import SessionRuntimeSnapshot
from .base import Session

logger = logging.getLogger(__name__)


class JsonSessionRepository:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, session_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, threading.RLock())

    @contextmanager
    def session_lock(self, session_id: str):
        with self._lock_for(session_id):
            yield

    def create(self, name: str) -> Session:
        now = time.time()
        session = Session(f"session_{uuid.uuid4().hex}", name.strip() or "新对话", now, now)
        self.save(session)
        return session

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"session_[A-Za-z0-9_-]+", session_id):
            raise SessionNotFoundError(f"会话不存在: {session_id}")
        target = (self.directory / f"{session_id}.json").resolve()
        if not target.is_relative_to(self.directory.resolve()):
            raise SessionNotFoundError(f"会话不存在: {session_id}")
        return target

    def get(self, session_id: str) -> Session:
        return self._read(session_id)

    def _read(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"会话不存在: {session_id}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return self._read_legacy(session_id, raw)
            return self._decode(raw)
        except SessionNotFoundError:
            raise
        except Exception as exc:
            raise SessionError(f"无法读取会话 {session_id}: {exc}") from exc

    def _read_legacy(self, session_id: str, messages: list[dict]) -> Session:
        meta_path = self.directory / f"{session_id}_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        now = time.time()
        return Session(session_id, meta.get("name", "旧会话"), float(meta.get("created_at", now)), float(meta.get("updated_at", now)), [self._message(item) for item in messages])

    def list(self) -> list[Session]:
        sessions = []
        for path in self.directory.glob("*.json"):
            if path.name.endswith("_meta.json"):
                continue
            try:
                sessions.append(self._read(path.stem))
            except SessionError as exc:
                logger.warning("跳过损坏会话 %s: %s", path, exc)
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def save(self, session: Session) -> None:
        with self._lock_for(session.id):
            payload = json.dumps(asdict(session), ensure_ascii=False, indent=2)
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, delete=False, suffix=".tmp") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temp_path = Path(handle.name)
                os.replace(temp_path, self._path(session.id))
            except OSError as exc:
                raise SessionError(f"无法保存会话 {session.id}: {exc}") from exc

    def append(self, session_id: str, message: Message) -> Session:
        with self._lock_for(session_id):
            session = self.get(session_id)
            session.messages.append(message)
            session.updated_at = time.time()
            self.save(session)
            return session

    def clear(self, session_id: str) -> Session:
        with self._lock_for(session_id):
            session = self.get(session_id)
            session.messages.clear()
            session.runtime_snapshot = None
            session.updated_at = time.time()
            self.save(session)
            return session

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"会话不存在: {session_id}")
        path.unlink()
        legacy_meta = self.directory / f"{session_id}_meta.json"
        if legacy_meta.exists():
            legacy_meta.unlink()

    def _decode(self, raw: dict) -> Session:
        runtime_raw = raw.get("runtime_snapshot")
        runtime = SessionRuntimeSnapshot.from_dict(runtime_raw) if isinstance(runtime_raw, dict) else None
        return Session(str(raw["id"]), str(raw["name"]), float(raw["created_at"]), float(raw["updated_at"]), [self._message(item) for item in raw.get("messages", [])], runtime, raw.get("model_profile_id"))

    @staticmethod
    def _message(raw: dict) -> Message:
        calls = [ToolCall(str(item["id"]), str(item["name"]), dict(item.get("arguments", {})), item.get("argument_error")) for item in raw.get("tool_calls", [])]
        attachment_ids = raw.get("attachment_ids", [])
        if not isinstance(attachment_ids, list):
            raise SessionError("消息附件引用格式错误")
        citations = raw.get("citations", [])
        if not isinstance(citations, list) or any(not isinstance(item, dict) for item in citations):
            citations = []
        return Message(role=raw["role"], content=raw.get("content", ""), tool_calls=calls, tool_call_id=raw.get("tool_call_id"), name=raw.get("name"), attachment_ids=attachment_ids, prompt_content=raw.get("prompt_content"), runtime_epoch=raw.get("runtime_epoch"), citations=citations, id=raw.get("id") or f"message_{uuid.uuid4().hex}")
