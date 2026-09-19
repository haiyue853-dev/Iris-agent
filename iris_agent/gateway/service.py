"""Gateway service: map platform users to sessions and run the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from iris_agent.core.agent import AgentService
from iris_agent.gateway.base import InboundMessage
from iris_agent.sessions.base import SessionRepository

if TYPE_CHECKING:
    from iris_agent.personal_assistant.service import PersonalAssistantService

_FILE_MARKER = re.compile(r"\[FILE:\s*([^\]]+?)\s*\]")
_APPROVAL_COMMAND = re.compile(r"^(确认|同意|执行|取消|拒绝)\s*(A-\d+)$", re.IGNORECASE)
_SECRET_KEY = re.compile(r"secret|password|token|api[_-]?key|authorization", re.IGNORECASE)


@dataclass(slots=True)
class GatewayReply:
    """The agent's reply plus any local files it asked to send.

    The agent declares files inline with ``[FILE:<absolute path>]`` markers,
    which the gateway strips from ``text`` and collects into ``files`` so the
    platform adapter can relay them (e.g. to a phone over QQ).
    """

    text: str
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PendingGatewayApproval:
    code: str
    session_id: str
    call_id: str
    tool_name: str
    arguments: dict


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
        personal_assistant: "PersonalAssistantService | None" = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.agent = agent
        self.sessions = sessions
        self.session_prefix = session_prefix
        self.state_file = state_file
        self.personal_assistant = personal_assistant
        self.workspace_root = workspace_root
        self._mapping: dict[tuple[str, str], str] = {}
        self._pending_approvals: dict[tuple[str, str], PendingGatewayApproval] = {}
        self._next_approval_number = 1
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

    def handle(self, message: InboundMessage) -> GatewayReply:
        """Answer an inbound message and return the final reply plus files."""
        text = message.text.strip()
        if not text:
            return GatewayReply(text="")
        personal_outcome = None
        if self.personal_assistant is not None and message.platform in {"qq", "wecom"}:
            personal_outcome = self.personal_assistant.ingest(message)
        approval_command = self._parse_approval_command(text)
        actor = (message.platform, str(message.user_id))
        if approval_command is not None:
            action, code = approval_command
            return self._resolve_approval(actor, code, action == "approve")
        if personal_outcome is not None:
            if personal_outcome.reply_override is not None:
                return GatewayReply(text=personal_outcome.reply_override)
        with self._lock:
            pending = self._pending_approvals.get(actor)
        if pending is not None:
            return GatewayReply(text=self._pending_reminder(pending))
        session_id = self.session_id(message.platform, message.user_id)
        reply_text = self._run(actor, session_id, text)
        reply = self._extract_files(reply_text)
        if personal_outcome is not None and personal_outcome.receipt:
            reply.text = f"{personal_outcome.receipt}\n\n{reply.text}" if reply.text else personal_outcome.receipt
        return reply

    @staticmethod
    def _extract_files(text: str) -> GatewayReply:
        files = [match.strip() for match in _FILE_MARKER.findall(text) if match.strip()]
        clean = _FILE_MARKER.sub("", text).strip()
        return GatewayReply(text=clean, files=files)

    def _run(self, actor: tuple[str, str], session_id: str, text: str) -> str:
        return self._consume_events(actor, session_id, self.agent.run(session_id, text))

    def _consume_events(self, actor: tuple[str, str], session_id: str, events) -> str:
        parts: list[str] = []
        fallback = ""
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
                pending = self._store_approval(actor, session_id, event.data)
                return self._approval_prompt(pending)
        return "".join(parts) or fallback

    @staticmethod
    def _parse_approval_command(text: str) -> tuple[str, str] | None:
        match = _APPROVAL_COMMAND.fullmatch(text.strip())
        if match is None:
            return None
        action = "approve" if match.group(1) in {"确认", "同意", "执行"} else "reject"
        return action, match.group(2).upper()

    def _store_approval(self, actor: tuple[str, str], session_id: str, data: dict) -> PendingGatewayApproval:
        with self._lock:
            code = f"A-{self._next_approval_number:03d}"
            self._next_approval_number += 1
            arguments = data.get("arguments")
            pending = PendingGatewayApproval(
                code=code,
                session_id=session_id,
                call_id=str(data.get("call_id", "")),
                tool_name=str(data.get("name") or "unknown"),
                arguments=dict(arguments) if isinstance(arguments, dict) else {},
            )
            self._pending_approvals[actor] = pending
            return pending

    def _resolve_approval(self, actor: tuple[str, str], code: str, approved: bool) -> GatewayReply:
        with self._lock:
            pending = self._pending_approvals.get(actor)
            if pending is None or pending.code != code:
                return GatewayReply(text=f"没有找到属于你的待确认操作【{code}】。")
            del self._pending_approvals[actor]
        events = self.agent.resolve_tool_approval(pending.session_id, pending.call_id, approved)
        text = self._consume_events(actor, pending.session_id, events)
        if approved:
            return self._extract_files(text or f"已确认并执行【{code}】。")
        prefix = f"已取消待确认操作【{code}】。"
        return GatewayReply(text=f"{prefix}\n\n{text}" if text else prefix)

    @classmethod
    def _approval_prompt(cls, pending: PendingGatewayApproval) -> str:
        details = cls._approval_details(pending.arguments)
        return (
            f"待确认操作【{pending.code}】\n"
            f"工具：{pending.tool_name}\n"
            f"参数：{details}\n\n"
            f"回复“确认 {pending.code}”执行，回复“取消 {pending.code}”取消。"
        )

    @staticmethod
    def _pending_reminder(pending: PendingGatewayApproval) -> str:
        return (
            f"还有待确认操作【{pending.code}】尚未处理。\n"
            f"回复“确认 {pending.code}”执行，回复“取消 {pending.code}”取消。"
        )

    @classmethod
    def _approval_details(cls, arguments: dict) -> str:
        safe = {
            str(key): "[已隐藏]" if _SECRET_KEY.search(str(key)) else value
            for key, value in arguments.items()
        }
        if "path" in safe:
            return f"目标文件 {safe['path']}"
        if "command" in safe:
            return f"命令 {safe['command']}"[:600]
        rendered = json.dumps(safe, ensure_ascii=False, default=str)
        return (rendered[:597] + "...") if len(rendered) > 600 else rendered

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
