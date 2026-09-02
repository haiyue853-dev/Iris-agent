from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import json
import os
from pathlib import Path
import tempfile
import time
import subprocess
from typing import Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from uuid import uuid4

import httpx


@dataclass(frozen=True, slots=True)
class McpServer:
    id: str
    name: str
    command: str
    args: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    enabled: bool = False
    environment: tuple[tuple[str, str], ...] = ()
    timeout_seconds: int = 10
    transport: str = "stdio"
    url: str = ""
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(slots=True)
class _McpProcessSession:
    process: subprocess.Popen[str]
    next_request_id: int = 2


@dataclass(slots=True)
class _McpHttpSession:
    client: httpx.Client
    next_request_id: int = 1
    session_id: str | None = None


class McpCenterService:
    """Stores MCP intent only. Starting a configured process is a separate approved action."""

    def __init__(self, settings_file: Path):
        self.settings_file = settings_file
        self._servers = self._load()
        self.events_file = settings_file.with_name("events.json")
        self._events = self._load_events()
        self.tools_file = settings_file.with_name("tools.json")
        self._tools = self._load_tools()
        self._sessions: dict[str, _McpProcessSession | _McpHttpSession] = {}

    def list(self) -> list[McpServer]:
        return sorted(self._servers.values(), key=lambda item: item.name.casefold())

    def is_connected(self, server_id: str) -> bool:
        """Whether this server currently has a live persistent stdio session."""
        self.get(server_id)
        session = self._sessions.get(server_id)
        return isinstance(session, _McpHttpSession) or (isinstance(session, _McpProcessSession) and session.process.poll() is None)

    def close(self) -> None:
        for server_id in tuple(self._sessions):
            self._close_session(server_id)

    def get(self, server_id: str) -> McpServer:
        return self._servers[server_id]

    def create(self, *, name: str, command: str = "", args: tuple[str, ...] = (), allowed_tools: tuple[str, ...] = (), transport: str = "stdio", url: str = "", headers: dict[str, str] | None = None) -> McpServer:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise ValueError("name is invalid")
        if transport not in {"stdio", "http"}:
            raise ValueError("transport is invalid")
        if transport == "stdio" and (not isinstance(command, str) or not command.strip() or any(char in command for char in "\r\n ;&|<>")):
            raise ValueError("command is invalid")
        if transport == "http" and not self._valid_url(url):
            raise ValueError("url is invalid")
        if not isinstance(args, tuple) or not all(isinstance(item, str) and "\x00" not in item for item in args):
            raise ValueError("args are invalid")
        if not isinstance(allowed_tools, tuple) or not all(isinstance(item, str) and item.strip() for item in allowed_tools):
            raise ValueError("allowed_tools are invalid")
        server = McpServer(str(uuid4()), name.strip(), command.strip(), args, tuple(dict.fromkeys(allowed_tools)), False, (), 10, transport, url.strip(), self._validate_headers(headers or {}))
        self._servers[server.id] = server
        self._save()
        return server

    def set_enabled(self, server_id: str, enabled: bool) -> McpServer:
        current = self.get(server_id)
        updated = self._updated(current, enabled=bool(enabled))
        self._servers[server_id] = updated
        self._save()
        if not enabled:
            self._close_session(server_id)
        return updated

    def set_allowed_tools(self, server_id: str, allowed_tools: tuple[str, ...]) -> McpServer:
        if not isinstance(allowed_tools, tuple) or not all(isinstance(item, str) and item.strip() for item in allowed_tools):
            raise ValueError("allowed_tools are invalid")
        current = self.get(server_id)
        updated = self._updated(current, allowed_tools=tuple(dict.fromkeys(allowed_tools)))
        self._servers[server_id] = updated
        self._save()
        return updated

    def set_environment(self, server_id: str, environment: dict[str, str]) -> McpServer:
        if not isinstance(environment, dict) or len(environment) > 50:
            raise ValueError("environment is invalid")
        if not all(isinstance(key, str) and key.replace("_", "a").isalnum() and key[:1].isalpha() and len(key) <= 100 and isinstance(value, str) and "\x00" not in value and len(value) <= 10_000 for key, value in environment.items()):
            raise ValueError("environment is invalid")
        current = self.get(server_id)
        updated = self._updated(current, environment=tuple(sorted(environment.items())))
        self._servers[server_id] = updated
        self._close_session(server_id)
        self._save()
        return updated

    def set_timeout_seconds(self, server_id: str, timeout_seconds: int) -> McpServer:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 120:
            raise ValueError("timeout_seconds is invalid")
        current = self.get(server_id)
        updated = self._updated(current, timeout_seconds=timeout_seconds)
        self._servers[server_id] = updated
        self._close_session(server_id)
        self._save()
        return updated

    def set_headers(self, server_id: str, headers: dict[str, str]) -> McpServer:
        current = self.get(server_id)
        updated = self._updated(current, headers=self._validate_headers(headers))
        self._servers[server_id] = updated
        self._close_session(server_id)
        self._save()
        return updated

    def delete(self, server_id: str) -> McpServer:
        server = self.get(server_id)
        del self._servers[server_id]
        self._close_session(server_id)
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
        except ValueError as exc:
            self._record_event(server.id, "discovery", False, started, failure_kind=self._failure_kind(exc))
            raise
        self._tools[server.id] = tools
        self._save_tools()
        self._record_event(server.id, "discovery", True, started)
        return tools

    def _discover(self, server: McpServer) -> tuple[dict[str, object], ...]:
        try:
            response = self._request(server, "tools/list", {})
            tools = response.get("result", {}).get("tools", []) if isinstance(response.get("result"), dict) else []
            return tuple(item for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str))
        except (OSError, TimeoutError, ValueError) as exc:
            self._close_session(server.id)
            raise ValueError("unable to discover MCP tools") from exc

    @staticmethod
    def _failure_kind(error: ValueError) -> str:
        current: BaseException | None = error
        while current is not None:
            if isinstance(current, FileNotFoundError):
                return "startup_failed"
            if isinstance(current, TimeoutError):
                return "timeout"
            if str(current) == "MCP tool returned an error":
                return "tool_error"
            current = current.__cause__
        return "protocol_error"

    def _record_event(self, server_id: str, kind: str, ok: bool, started: float, tool_name: str | None = None, failure_kind: str | None = None) -> None:
        event: dict[str, object] = {
            "server_id": server_id,
            "kind": kind,
            "ok": ok,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at": time.time(),
        }
        if tool_name is not None:
            event["tool_name"] = tool_name
        if failure_kind is not None:
            event["failure_kind"] = failure_kind
        self._events.append(event)
        self._save_events()

    def enabled_tools(self, discovered_by_server: dict[str, tuple[dict[str, object], ...]] | None = None, *, cached_only: bool = False) -> tuple[tuple[McpServer, dict[str, object]], ...]:
        """Return discoverable tools from enabled servers, restricted to each allowlist."""
        discovered: list[tuple[McpServer, dict[str, object]]] = []
        for server in self.list():
            if not server.enabled:
                continue
            if discovered_by_server is None:
                if cached_only:
                    tools = self.cached_tools(server.id)
                else:
                    try:
                        tools = self.discover_tools(server.id)
                    except ValueError:
                        continue
            else:
                tools = discovered_by_server.get(server.id, ())
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
            if isinstance(result, dict) and result.get("isError") is True:
                raise ValueError("MCP tool returned an error")
        except ValueError as exc:
            self._record_event(server.id, "tool_call", False, started, name, self._failure_kind(exc))
            raise
        self._record_event(server.id, "tool_call", True, started, name)
        return result

    def _call(self, server: McpServer, name: str, arguments: dict[str, object]) -> object:
        try:
            response = self._request(server, "tools/call", {"name": name, "arguments": arguments})
            if not isinstance(response.get("result"), dict):
                raise ValueError("MCP returned an invalid result")
            return response["result"]
        except (OSError, TimeoutError, ValueError) as exc:
            self._close_session(server.id)
            raise ValueError("unable to call MCP tool") from exc

    def _request(self, server: McpServer, method: str, params: dict[str, object]) -> dict[str, object]:
        if server.transport == "http":
            return self._http_request(server, method, params)
        session = self._session(server)
        assert isinstance(session, _McpProcessSession)
        process = session.process
        assert process.stdin is not None
        request_id = session.next_request_id
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        response = self._read_response(process, request_id, server.timeout_seconds)
        session.next_request_id += 1
        return response

    def _session(self, server: McpServer) -> _McpProcessSession:
        session = self._sessions.get(server.id)
        if session is not None and session.process.poll() is None:
            return session
        self._close_session(server.id)
        try:
            process = subprocess.Popen(
                self._command_args(server), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=self._subprocess_env(server),
            )
            assert process.stdin is not None
            process.stdin.write('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"iris-agent","version":"0.1"}}}\n')
            process.stdin.flush()
            self._read_response(process, 1, server.timeout_seconds)
            process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n')
            process.stdin.flush()
        except (OSError, TimeoutError, ValueError) as exc:
            try:
                process.terminate()
            except UnboundLocalError:
                pass
            raise ValueError("unable to start MCP session") from exc
        session = _McpProcessSession(process)
        self._sessions[server.id] = session
        return session

    def _close_session(self, server_id: str) -> None:
        session = self._sessions.pop(server_id, None)
        if session is None:
            return
        if isinstance(session, _McpHttpSession):
            session.client.close()
            return
        session.process.terminate()
        try:
            session.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            session.process.kill()

    def _http_request(self, server: McpServer, method: str, params: dict[str, object]) -> dict[str, object]:
        session = self._sessions.get(server.id)
        if not isinstance(session, _McpHttpSession):
            session = _McpHttpSession(httpx.Client(timeout=server.timeout_seconds, headers={"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26", **dict(server.headers)}))
            self._sessions[server.id] = session
            if method != "initialize":
                self._http_request(server, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "iris-agent", "version": "0.1"}})
        request_id = session.next_request_id
        headers = {"Content-Type": "application/json"}
        if session.session_id:
            headers["Mcp-Session-Id"] = session.session_id
        try:
            response = session.client.post(server.url, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, headers=headers)
            response.raise_for_status()
            session.session_id = response.headers.get("mcp-session-id", session.session_id)
            payload: Any = response.json() if "text/event-stream" not in response.headers.get("content-type", "") else self._sse_payload(response.text)
            if not isinstance(payload, dict) or payload.get("id") != request_id or "error" in payload:
                raise ValueError("MCP returned an invalid response")
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            self._close_session(server.id)
            raise ValueError("MCP HTTP request failed") from exc
        session.next_request_id += 1
        return payload

    @staticmethod
    def _sse_payload(text: str) -> dict[str, object]:
        for event in text.split("\n\n"):
            data = "\n".join(line[5:].strip() for line in event.splitlines() if line.startswith("data:"))
            if data:
                payload = json.loads(data)
                if isinstance(payload, dict):
                    return payload
        raise ValueError("MCP returned an empty SSE response")

    @staticmethod
    def _valid_url(value: str) -> bool:
        try:
            parsed = httpx.URL(value.strip())
            return parsed.scheme in {"http", "https"} and bool(parsed.host) and not parsed.username and not parsed.password
        except Exception:
            return False

    @staticmethod
    def _validate_headers(headers: dict[str, str]) -> tuple[tuple[str, str], ...]:
        if not isinstance(headers, dict) or len(headers) > 50 or not all(isinstance(key, str) and key.strip() and "\r" not in key and "\n" not in key and isinstance(value, str) and "\r" not in value and "\n" not in value and len(value) <= 10_000 for key, value in headers.items()):
            raise ValueError("headers are invalid")
        return tuple(sorted((key.strip(), value) for key, value in headers.items()))

    @staticmethod
    def _updated(server: McpServer, **changes: Any) -> McpServer:
        values = {field: getattr(server, field) for field in McpServer.__dataclass_fields__}
        values.update(changes)
        return McpServer(**values)

    @staticmethod
    def _subprocess_env(server: McpServer) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(dict(server.environment))
        if os.name == "nt" and server.command.casefold() in {"node", "node.exe"}:
            node_dir = Path(environment.get("ProgramFiles", r"C:\Program Files")) / "nodejs"
            if (node_dir / "node.exe").is_file() and node_dir.as_posix().casefold() not in environment.get("PATH", "").casefold():
                environment["PATH"] = f"{node_dir}{os.pathsep}{environment.get('PATH', '')}"
        return environment

    @staticmethod
    def _command_args(server: McpServer) -> list[str]:
        command = server.command
        if os.name == "nt" and command.casefold() in {"node", "node.exe"}:
            node_executable = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"
            if node_executable.is_file():
                command = str(node_executable)
        return [command, *server.args]

    @staticmethod
    def _read_response(process: subprocess.Popen[str], expected_id: int, timeout_seconds: int) -> dict[str, object]:
        assert process.stdout is not None
        with ThreadPoolExecutor(max_workers=1) as pool:
            while True:
                line = pool.submit(process.stdout.readline).result(timeout=timeout_seconds)
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
                item["id"]: McpServer(item["id"], item["name"], item.get("command", ""), tuple(item.get("args", ())), tuple(item["allowed_tools"]), bool(item.get("enabled", False)), tuple(sorted((key, value) for key, value in item.get("environment", {}).items() if isinstance(key, str) and isinstance(value, str))), item.get("timeout_seconds", 10), item.get("transport", "stdio"), item.get("url", ""), tuple(sorted((key, value) for key, value in item.get("headers", {}).items() if isinstance(key, str) and isinstance(value, str))))
                for item in raw.get("servers", [])
            }
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": [
            {"id": item.id, "name": item.name, "command": item.command, "args": list(item.args), "allowed_tools": list(item.allowed_tools), "enabled": item.enabled, "environment": dict(item.environment), "timeout_seconds": item.timeout_seconds, "transport": item.transport, "url": item.url, "headers": dict(item.headers)}
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
                {key: item[key] for key in ("server_id", "kind", "ok", "duration_ms", "created_at", "tool_name", "failure_kind") if key in item}
                for item in events
                if isinstance(item, dict)
                and isinstance(item.get("server_id"), str)
                and item.get("kind") in {"discovery", "tool_call"}
                and isinstance(item.get("ok"), bool)
                and isinstance(item.get("duration_ms"), (int, float))
                and isinstance(item.get("created_at"), (int, float))
                and ("tool_name" not in item or isinstance(item["tool_name"], str))
                and ("failure_kind" not in item or item["failure_kind"] in {"startup_failed", "timeout", "protocol_error", "tool_error", "unknown"})
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
