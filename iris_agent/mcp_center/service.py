from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class McpServer:
    id: str
    name: str
    command: str
    args: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    enabled: bool = False


class McpCenterService:
    """Stores MCP intent only. Starting a configured process is a separate approved action."""

    def __init__(self, settings_file: Path):
        self.settings_file = settings_file
        self._servers = self._load()

    def list(self) -> list[McpServer]:
        return sorted(self._servers.values(), key=lambda item: item.name.casefold())

    def get(self, server_id: str) -> McpServer:
        return self._servers[server_id]

    def create(self, *, name: str, command: str, args: tuple[str, ...], allowed_tools: tuple[str, ...]) -> McpServer:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise ValueError("name is invalid")
        if not isinstance(command, str) or not command.strip() or any(char in command for char in "\r\n ;&|<>"):
            raise ValueError("command is invalid")
        if not isinstance(args, tuple) or not all(isinstance(item, str) and "\x00" not in item for item in args):
            raise ValueError("args are invalid")
        if not isinstance(allowed_tools, tuple) or not all(isinstance(item, str) and item.strip() for item in allowed_tools):
            raise ValueError("allowed_tools are invalid")
        server = McpServer(str(uuid4()), name.strip(), command.strip(), args, tuple(dict.fromkeys(allowed_tools)))
        self._servers[server.id] = server
        self._save()
        return server

    def set_enabled(self, server_id: str, enabled: bool) -> McpServer:
        current = self.get(server_id)
        updated = McpServer(current.id, current.name, current.command, current.args, current.allowed_tools, bool(enabled))
        self._servers[server_id] = updated
        self._save()
        return updated

    def _load(self) -> dict[str, McpServer]:
        if not self.settings_file.is_file():
            return {}
        try:
            raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return {
                item["id"]: McpServer(item["id"], item["name"], item["command"], tuple(item["args"]), tuple(item["allowed_tools"]), bool(item.get("enabled", False)))
                for item in raw.get("servers", [])
            }
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": [
            {"id": item.id, "name": item.name, "command": item.command, "args": list(item.args), "allowed_tools": list(item.allowed_tools), "enabled": item.enabled}
            for item in self.list()
        ]}
        fd, temporary = tempfile.mkstemp(dir=self.settings_file.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.settings_file)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
