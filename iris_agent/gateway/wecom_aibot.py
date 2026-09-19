"""Official WeCom intelligent-robot long-connection bridge.

The WeCom protocol is handled by the official Node SDK in a child process.
Python and Node exchange newline-delimited JSON over stdio, keeping the bot
credentials off command lines and out of the repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Callable
from uuid import uuid4

from iris_agent.gateway.base import InboundMessage
from iris_agent.gateway.service import GatewayService


_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class WeComAIBotBridge:
    gateway: GatewayService
    bot_id: str = field(repr=False)
    secret: str = field(repr=False)
    script_path: Path
    owner_file: Path
    respond_groups: bool = False
    allowed_users: tuple[str, ...] = ()
    allow_all: bool = False
    node_executable: str = "node"
    process_factory: Callable[..., Any] = field(default=subprocess.Popen, repr=False)
    send_timeout_seconds: float = 10.0
    _process: Any = field(default=None, init=False, repr=False)
    _status: str = field(default="stopped", init=False)
    _owner_user_id: str = field(default="", init=False, repr=False)
    _write_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _owner_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _send_waiters: dict[str, tuple[threading.Event, dict[str, bool]]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.script_path = Path(self.script_path)
        self.owner_file = Path(self.owner_file)
        self.allowed_users = tuple(str(item).strip() for item in self.allowed_users if str(item).strip())
        self._owner_user_id = self._load_owner()

    @property
    def owner_user_id(self) -> str:
        return self._owner_user_id

    @property
    def connected(self) -> bool:
        return self._status == "authenticated" and self._process is not None and self._process.poll() is None

    @property
    def status(self) -> str:
        return self._status

    def start(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True
        if not self.bot_id.strip() or not self.secret.strip():
            _LOGGER.warning("企业微信智能机器人未启动：缺少 Bot ID 或 Secret")
            self._status = "not_configured"
            return False
        script_path = self.script_path.resolve()
        if not script_path.is_file():
            _LOGGER.warning("企业微信智能机器人桥接脚本不存在：%s", script_path)
            self._status = "script_missing"
            return False
        child_env = os.environ.copy()
        child_env["IRIS_WECOM_BOT_ID"] = self.bot_id
        child_env["IRIS_WECOM_BOT_SECRET"] = self.secret
        kwargs: dict[str, Any] = {
            "cwd": str(script_path.parent),
            "env": child_env,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "bufsize": 1,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self._process = self.process_factory([self.node_executable, str(script_path)], **kwargs)
        except OSError:
            _LOGGER.exception("企业微信智能机器人桥接进程启动失败")
            self._status = "start_failed"
            return False
        self._status = "connecting"
        threading.Thread(target=self._read_stdout, name="iris-wecom-aibot", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="iris-wecom-aibot-log", daemon=True).start()
        return True

    def stop(self) -> None:
        process = self._process
        if process is None:
            self._status = "stopped"
            return
        if process.poll() is None:
            self._write({"type": "shutdown"})
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _LOGGER.warning("企业微信智能机器人桥接进程未能及时退出")
        self._process = None
        self._status = "stopped"

    def handle_message_event(self, event: dict[str, Any]) -> dict[str, str]:
        event_id = str(event.get("event_id", ""))
        chat_type = str(event.get("chat_type", "single"))
        user_id = str(event.get("user_id", "")).strip()
        if chat_type != "single" and not self.respond_groups:
            return {"type": "reply", "event_id": event_id, "text": "这是私人助手，目前仅开放私聊。"}
        if not user_id:
            return {"type": "reply", "event_id": event_id, "text": "未能识别发送者，消息没有处理。"}
        if not self._is_authorized(user_id):
            return {"type": "reply", "event_id": event_id, "text": "当前账号未授权使用这个私人助手。"}
        message = InboundMessage(
            "wecom",
            user_id,
            str(event.get("text", "")),
            raw={
                "message_id": str(event.get("message_id", "")),
                "chat_id": str(event.get("chat_id", "")),
                "chat_type": chat_type,
            },
        )
        try:
            reply = self.gateway.handle(message)
            text = reply.text or "已处理。"
        except Exception:
            _LOGGER.exception("处理企业微信消息失败")
            text = "抱歉，处理这条消息时出错了，请稍后再试。"
        return {"type": "reply", "event_id": event_id, "text": text}

    def send_text(self, chat_id: str, text: str) -> bool:
        if not self.connected or not text.strip():
            return False
        request_id = uuid4().hex
        completed = threading.Event()
        result = {"ok": False}
        self._send_waiters[request_id] = (completed, result)
        if not self._write({"type": "send", "request_id": request_id, "chat_id": str(chat_id), "text": text}):
            self._send_waiters.pop(request_id, None)
            return False
        completed.wait(self.send_timeout_seconds)
        self._send_waiters.pop(request_id, None)
        return result["ok"]

    def _is_authorized(self, user_id: str) -> bool:
        if self.allow_all:
            return True
        if self.allowed_users:
            return user_id in self.allowed_users
        with self._owner_lock:
            if self._owner_user_id:
                return user_id == self._owner_user_id
            self.owner_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.owner_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({"user_id": user_id}, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.owner_file)
            self._owner_user_id = user_id
            return True

    def _load_owner(self) -> str:
        try:
            value = json.loads(self.owner_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        return str(value.get("user_id", "")).strip() if isinstance(value, dict) else ""

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                _LOGGER.warning("忽略无法解析的企业微信桥接输出")
                continue
            self._dispatch_event(event)
        if self._process is process and process.poll() is not None:
            self._status = "stopped"

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            line = line.rstrip()
            if line:
                _LOGGER.info("WeCom bridge: %s", line)

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "status":
            self._status = str(event.get("status", "unknown"))
            return
        if event_type == "message":
            threading.Thread(target=self._answer_message, args=(event,), daemon=True).start()
            return
        if event_type == "send_result":
            request_id = str(event.get("request_id", ""))
            waiter = self._send_waiters.get(request_id)
            if waiter is not None:
                completed, result = waiter
                result["ok"] = bool(event.get("ok"))
                completed.set()

    def _answer_message(self, event: dict[str, Any]) -> None:
        self._write(self.handle_message_event(event))

    def _write(self, payload: dict[str, Any]) -> bool:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            return False
        try:
            with self._write_lock:
                process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                process.stdin.flush()
            return True
        except (OSError, ValueError):
            _LOGGER.exception("写入企业微信桥接进程失败")
            return False
