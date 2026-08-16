"""QQ adapter over the OneBot 11 reverse-WebSocket protocol.

A OneBot implementation (NapCat, LLOneBot, ...) connects to our WebSocket
endpoint as a client and pushes events.  We parse ``message`` events, run the
agent, and return a list of OneBot actions (file sends + a text reply) that the
endpoint relays back over the same connection.  Private messages are always
answered; group messages are answered only when ``respond_groups`` is enabled.
"""

from __future__ import annotations

from uuid import uuid4

from iris_agent.gateway.base import InboundMessage
from iris_agent.gateway.service import GatewayReply, GatewayService


class QQOneBotAdapter:
    name = "qq"

    def __init__(self, gateway: GatewayService, respond_groups: bool = False) -> None:
        self.gateway = gateway
        self.respond_groups = respond_groups

    def handle_event(self, payload: dict) -> list[dict]:
        """Turn an inbound OneBot event into a list of actions (possibly empty)."""
        if not isinstance(payload, dict) or payload.get("post_type") != "message":
            return []
        message_type = payload.get("message_type")
        text = self._extract_text(payload)
        if not text:
            return []

        if message_type == "private":
            user_id = str(payload.get("user_id", ""))
            if not user_id:
                return []
            reply = self._safe_reply(user_id, text, payload)
            return self._build_actions("private", reply, user_id=user_id)

        if message_type == "group":
            if not self.respond_groups:
                return []
            group_id = str(payload.get("group_id", ""))
            user_id = str(payload.get("user_id", ""))
            if not group_id or not user_id:
                return []
            reply = self._safe_reply(user_id, text, payload)
            return self._build_actions("group", reply, group_id=group_id)

        return []

    def _safe_reply(self, user_id: str, text: str, payload: dict) -> GatewayReply:
        try:
            return self.gateway.handle(InboundMessage("qq", user_id, text, raw=payload))
        except Exception as exc:  # noqa: BLE001 - surface a friendly error to the user
            return GatewayReply(text=f"抱歉，处理你的消息时出错了：{exc}")

    def _build_actions(
        self,
        message_type: str,
        reply: GatewayReply,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> list[dict]:
        actions: list[dict] = []
        # Files are relayed only for private chats (the "send to my phone" case).
        if message_type == "private" and user_id is not None:
            for path in reply.files:
                actions.append(self._send_file_action(user_id, path))
        if reply.text:
            actions.append(self._send_action(message_type, text=reply.text, user_id=user_id, group_id=group_id))
        return actions

    @staticmethod
    def _extract_text(payload: dict) -> str:
        segments = payload.get("message")
        if isinstance(segments, list):
            parts = [
                str((segment.get("data") or {}).get("text", ""))
                for segment in segments
                if isinstance(segment, dict) and segment.get("type") == "text"
            ]
            text = "".join(parts).strip()
            if text:
                return text
        return str(payload.get("raw_message", "")).strip()

    @staticmethod
    def _send_action(message_type: str, text: str, user_id: str | None = None, group_id: str | None = None) -> dict:
        params: dict = {"message_type": message_type, "message": text}
        if message_type == "private" and user_id is not None:
            params["user_id"] = int(user_id)
        elif message_type == "group" and group_id is not None:
            params["group_id"] = int(group_id)
        return {"action": "send_msg", "params": params, "echo": str(uuid4())}

    @staticmethod
    def _send_file_action(user_id: str, path: str) -> dict:
        """Build a ``send_msg`` action carrying a local file via a CQ ``file`` segment."""
        normalized = path.replace("\\", "/")
        name = normalized.rsplit("/", 1)[-1]
        message = f"[CQ:file,file=file:///{normalized},name={name}]"
        return {"action": "send_msg", "params": {"message_type": "private", "user_id": int(user_id), "message": message}, "echo": str(uuid4())}
