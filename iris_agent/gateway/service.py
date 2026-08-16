"""Gateway service: map platform users to sessions and run the agent."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from iris_agent.core.agent import AgentService
from iris_agent.gateway.base import InboundMessage
from iris_agent.sessions.base import SessionRepository


class GatewayService:
    """Owns the platform→session mapping and answers inbound messages.

    Session ids are stable per ``(platform, user_id)`` and persisted to a small
    JSON file so conversation context survives restarts.  The mapping reuses the
    regular :class:`SessionRepository`, so every platform user gets an isolated
    session that also shows up in the web session list.
    """

    def __init__(
        self,
        agent: AgentService,
        sessions: SessionRepository,
        session_prefix: str = "gateway",
        state_file: Path | None = None,
    ) -> None:
        self.agent = agent
        self.sessions = sessions
        self.session_prefix = session_prefix
        self.state_file = state_file
        self._mapping: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()
        self._load_state()

    # ---- session mapping -------------------------------------------------

    def session_id(self, platform: str, user_id: str) -> str:
        key = (platform, str(user_id))
        with self._lock:
            session_id = self._mapping.get(key)
            if session_id is None:
                session = self.sessions.create(f"{self.session_prefix}-{platform}-{user_id}")
                session_id = session.id
                self._mapping[key] = session_id
                self._save_state()
            return session_id

    # ---- message handling -----------------------------------------------

    def handle(self, message: InboundMessage) -> str:
        """Answer an inbound message and return the final reply text."""
        text = message.text.strip()
        if not text:
            return ""
        session_id = self.session_id(message.platform, message.user_id)
        return self._run(session_id, text)

    def _run(self, session_id: str, text: str) -> str:
        parts: list[str] = []
        fallback = ""
        events = self.agent.run(session_id, text)
        while True:
            pending: str | None = None
            for event in events:
                if event.type == "text_delta":
                    # AgentService strips content from ``message_completed`` and
                    # streams it via ``text_delta`` instead, so accumulate those.
                    parts.append(str(event.data.get("content", "")))
                elif event.type == "message_completed":
                    content = str(event.data.get("content", ""))
                    if content:
                        fallback = content
                elif event.type == "tool_approval_requested":
                    # No approval UI on chat platforms; refuse non-read-only tools.
                    pending = str(event.data.get("call_id", ""))
                    break
            if pending is None:
                return "".join(parts) or fallback
            events = self.agent.resolve_tool_approval(session_id, pending, False)

    # ---- mapping persistence --------------------------------------------

    def _load_state(self) -> None:
        if self.state_file is None or not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        mapping = raw.get("mapping", {})
        if isinstance(mapping, dict):
            self._mapping = {
                tuple(str(k).split(":", 1)): str(v)
                for k, v in mapping.items()
                if ":" in str(k)
            }

    def _save_state(self) -> None:
        if self.state_file is None:
            return
        payload = {"mapping": {f"{platform}:{user_id}": session_id for (platform, user_id), session_id in self._mapping.items()}}
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.state_file)
        except OSError:
            pass
