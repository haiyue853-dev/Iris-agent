from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import json
import os
from pathlib import Path
import tempfile
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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
        self.events_file = settings_file.with_name("events.json")
        self._events = self._load_events()
        self.tools_file = settings_file.with_name("tools.json")
        self._tools = self._load_tools()

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

    def set_allowed_tools(self, server_id: str, allowed_tools: tuple[str, ...]) -> McpServer:
        if not isinstance(allowed_tools, tuple) or not all(isinstance(item, str) and item.strip() for item in allowed_tools):
            raise ValueError("allowed_tools are invalid")
        current = self.get(server_id)
        updated = McpServer(current.id, current.name, current.command, current.args, tuple(dict.fromkeys(allowed_tools)), current.enabled)
        self._servers[server_id] = updated
        self._save()
        return updated

    def delete(self, server_id: str) -> McpServer:
        server = self.get(server_id)
        del self._servers[server_id]
        self._save()
        self._events = deque((event for event in self._events if event["server_id"] != server_id), maxlen=50)
        self._save_events()
        self._tools.pop(server_id, None)
        self._save_tools()
        return server

    def events(self, server_id: str) -> tuple[dict[str, object], ...]:
        self.get(server_id)
        return tuple(event for event in reversed(self._events) if event["server_id"] == server_id)

    def cached_tools(self, server_id: str) -> tuple[dict[str, object], ...]:
        self.get(server_id)
        return tuple(self._tools.get(server_id, ()))

    def discover_tools(self, server_id: str) -> tuple[dict[str, object], ...]:
        """Run only the MCP handshake and tools/list request, then terminate the child."""
        server = self.get(server_id)
        if not server.enabled:
            raise ValueError("server is disabled")
        started = time.perf_counter()
        try:
            tools = self._discover(server)
        except ValueError:
            self._record_event(server.id, "discovery", False, started)
            raise
        self._tools[server.id] = tools
        self._save_tools()
        self._record_event(server.id, "discovery", True, started)
        return tools

    def _discover(self, server: McpServer) -> tuple[dict[str, object], ...]:
        process = subprocess.Popen(
            [server.command, *server.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"iris-agent","version":"0.1"}}}\n')
            process.stdin.flush()
            self._read_response(process, 1)
            process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n')
            process.stdin.flush()
            response = self._read_response(process, 2)
            tools = response.get("result", {}).get("tools", []) if isinstance(response.get("result"), dict) else []
            return tuple(item for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str))
        except (OSError, TimeoutError, ValueError) as exc:
            raise ValueError("unable to discover MCP tools") from exc
        finally:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill()

    def _record_event(self, server_id: str, kind: str, ok: bool, started: float, tool_name: str | None = None) -> None:
        event: dict[str, object] = {
            "server_id": server_id,
            "kind": kind,
            "ok": ok,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at": time.time(),
        }
        if tool_name is not None:
            event["tool_name"] = tool_name
        self._events.append(event)
        self._save_events()

    def enabled_tools(self) -> tuple[tuple[McpServer, dict[str, object]], ...]:
        """Return discoverable tools from enabled servers, restricted to each allowlist."""
        discovered: list[tuple[McpServer, dict[str, object]]] = []
        for server in self.list():
            if not server.enabled:
                continue
            try:
                tools = self.discover_tools(server.id)
            except ValueError:
                continue
            for tool in tools:
                name = tool.get("name")
                schema = tool.get("inputSchema")
                if name in server.allowed_tools and isinstance(schema, dict) and schema.get("type") == "object":
                    discovered.append((server, tool))
        return tuple(discovered)

    def call_tool(self, server_id: str, name: str, arguments: dict[str, object]) -> object:
        server = self.get(server_id)
        if not server.enabled or name not in server.allowed_tools or not isinstance(arguments, dict):
            raise ValueError("MCP tool is not allowed")
        started = time.perf_counter()
        try:
            result = self._call(server, name, arguments)
        except ValueError:
            self._record_event(server.id, "tool_call", False, started, name)
            raise
        self._record_event(server.id, "tool_call", True, started, name)
        return result

    def _call(self, server: McpServer, name: str, arguments: dict[str, object]) -> object:
        process = subprocess.Popen(
            [server.command, *server.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        )
        try:
            assert process.stdin is not None
            process.stdin.write('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"iris-agent","version":"0.1"}}}\n')
            process.stdin.flush()
            self._read_response(process, 1)
            request = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n" + json.dumps(request) + "\n")
            process.stdin.flush()
            response = self._read_response(process, 2)
            if not isinstance(response.get("result"), dict):
                raise ValueError("MCP returned an invalid result")
            return response["result"]
        except (OSError, TimeoutError, ValueError) as exc:
            raise ValueError("unable to call MCP tool") from exc
        finally:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill()

    @staticmethod
    def _read_response(process: subprocess.Popen[str], expected_id: int) -> dict[str, object]:
        assert process.stdout is not None
        with ThreadPoolExecutor(max_workers=1) as pool:
            while True:
                line = pool.submit(process.stdout.readline).result(timeout=10)
                if not line: raise ValueError("MCP process ended")
                message = json.loads(line)
                if message.get("id") == expected_id:
                    if "error" in message: raise ValueError("MCP returned an error")
                    return message

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

    def _load_events(self) -> deque[dict[str, object]]:
        if not self.events_file.is_file():
            return deque(maxlen=50)
        try:
            raw = json.loads(self.events_file.read_text(encoding="utf-8"))
            events = raw.get("events", [])
            if not isinstance(events, list):
                return deque(maxlen=50)
            safe = [
                {key: item[key] for key in ("server_id", "kind", "ok", "duration_ms", "created_at", "tool_name") if key in item}
                for item in events
                if isinstance(item, dict)
                and isinstance(item.get("server_id"), str)
                and item.get("kind") in {"discovery", "tool_call"}
                and isinstance(item.get("ok"), bool)
                and isinstance(item.get("duration_ms"), (int, float))
                and isinstance(item.get("created_at"), (int, float))
                and ("tool_name" not in item or isinstance(item["tool_name"], str))
            ]
            return deque(safe[-50:], maxlen=50)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return deque(maxlen=50)

    def _save_events(self) -> None:
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.events_file.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"events": list(self._events)}, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.events_file)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _load_tools(self) -> dict[str, tuple[dict[str, object], ...]]:
        if not self.tools_file.is_file():
            return {}
        try:
            raw = json.loads(self.tools_file.read_text(encoding="utf-8"))
            cached = raw.get("tools", {})
            if not isinstance(cached, dict):
                return {}
            return {
                server_id: tuple(item for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str))
                for server_id, tools in cached.items()
                if isinstance(server_id, str) and isinstance(tools, list)
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save_tools(self) -> None:
        self.tools_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.tools_file.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"tools": self._tools}, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.tools_file)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
