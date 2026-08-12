from pathlib import Path
import io
import json
import subprocess

from iris_agent.mcp_center.service import McpCenterService


def test_mcp_server_is_persisted_with_a_tool_allowlist(tmp_path: Path) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser MCP", command="node", args=("D:/agent/browser-mcp/browser-mcp-server-v2.js",), allowed_tools=("get_page_content",))
    assert server.enabled is False
    assert McpCenterService(tmp_path / "mcp.json").get(server.id) == server


def test_mcp_server_rejects_an_unsafe_command(tmp_path: Path) -> None:
    try:
        McpCenterService(tmp_path / "mcp.json").create(name="bad", command="cmd.exe /c whoami", args=(), allowed_tools=())
    except ValueError as exc:
        assert "command" in str(exc)
    else:
        raise AssertionError("unsafe command was accepted")


def test_mcp_server_updates_its_tool_allowlist(tmp_path: Path) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())

    updated = service.set_allowed_tools(server.id, ("get_page", "get_tabs"))

    assert updated.allowed_tools == ("get_page", "get_tabs")
    assert McpCenterService(tmp_path / "mcp.json").get(server.id).allowed_tools == ("get_page", "get_tabs")


def test_mcp_server_persists_valid_environment_variables(tmp_path: Path) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Search", command="node", args=("server.js",), allowed_tools=())

    updated = service.set_environment(server.id, {"SEARCH_API_KEY": "secret", "REGION": "cn"})

    assert updated.environment == (("REGION", "cn"), ("SEARCH_API_KEY", "secret"))
    assert McpCenterService(tmp_path / "mcp.json").get(server.id).environment == updated.environment


def test_mcp_server_delete_removes_its_local_configuration(tmp_path: Path) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())

    deleted = service.delete(server.id)

    assert deleted.id == server.id
    assert service.list() == []
    assert McpCenterService(tmp_path / "mcp.json").list() == []


def test_mcp_events_record_only_safe_discovery_metadata(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_discover", lambda item: ({"name": "get_page"},))

    service.discover_tools(server.id)

    event = service.events(server.id)[0]
    assert event["kind"] == "discovery"
    assert event["ok"] is True
    assert event["duration_ms"] >= 0
    assert "arguments" not in event and "result" not in event and "error" not in event


def test_mcp_missing_command_is_a_safe_discovery_failure(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    service.set_enabled(server.id, True)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("node not found")))

    try:
        service.discover_tools(server.id)
    except ValueError as exc:
        assert "unable to discover MCP tools" in str(exc)
    else:
        raise AssertionError("missing MCP command was not reported as a discovery error")

    assert service.events(server.id)[0]["ok"] is False


def test_mcp_uses_windows_node_fallback_when_node_is_not_on_path(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())

    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setenv("ProgramFiles", "C:\\Program Files")
    monkeypatch.setattr("iris_agent.mcp_center.service.Path.is_file", lambda path: str(path) == "C:\\Program Files\\nodejs\\node.exe")

    environment = service._subprocess_env(server)

    assert environment["PATH"].startswith("C:\\Program Files\\nodejs")


def test_mcp_resolves_windows_node_fallback_to_an_executable_path(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())

    monkeypatch.setenv("ProgramFiles", "C:\\Program Files")
    monkeypatch.setattr("iris_agent.mcp_center.service.Path.is_file", lambda path: str(path) == "C:\\Program Files\\nodejs\\node.exe")

    assert service._command_args(server)[0] == "C:\\Program Files\\nodejs\\node.exe"


def test_mcp_events_record_safe_tool_call_metadata(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_call", lambda item, name, arguments: {"content": [{"text": "secret"}]})

    service.call_tool(server.id, "get_page", {"url": "https://private.example"})

    event = service.events(server.id)[0]
    assert event["kind"] == "tool_call"
    assert event["tool_name"] == "get_page"
    assert event["ok"] is True
    assert "arguments" not in event and "result" not in event and "error" not in event


def test_two_mcp_calls_reuse_one_initialized_process(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("navigate", "get_page_source"))
    service.set_enabled(server.id, True)
    starts = 0

    class Process:
        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"jsonrpc":"2.0","id":1,"result":{}}\n'
                '{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"navigated"}]}}\n'
                '{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"<title>Example</title>"}]}}\n'
            )

        def terminate(self) -> None:
            pass

        def poll(self):
            return None

        def wait(self, timeout: float) -> None:
            pass

    def start(*args, **kwargs):
        nonlocal starts
        starts += 1
        return Process()

    monkeypatch.setattr(subprocess, "Popen", start)

    service.call_tool(server.id, "navigate", {"url": "https://example.test"})
    result = service.call_tool(server.id, "get_page_source", {})

    assert starts == 1
    assert result == {"content": [{"type": "text", "text": "<title>Example</title>"}]}


def test_disabling_or_deleting_server_closes_its_live_session(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page_source",))
    service.set_enabled(server.id, True)

    class Process:
        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"jsonrpc":"2.0","id":1,"result":{}}\n'
                '{"jsonrpc":"2.0","id":2,"result":{"content":[]}}\n'
            )
            self.terminated = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float) -> None:
            pass

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    service.call_tool(server.id, "get_page_source", {})
    service.set_enabled(server.id, False)

    assert process.terminated is True


def test_close_releases_all_live_mcp_sessions(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page_source",))
    service.set_enabled(server.id, True)

    class Process:
        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = io.StringIO('{"jsonrpc":"2.0","id":1,"result":{}}\n{"jsonrpc":"2.0","id":2,"result":{"content":[]}}\n')
            self.terminated = False

        def poll(self): return None
        def terminate(self): self.terminated = True
        def wait(self, timeout: float): pass

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    service.call_tool(server.id, "get_page_source", {})
    service.close()

    assert process.terminated is True


def test_mcp_error_result_is_recorded_as_a_failed_tool_call(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_call", lambda item, name, arguments: {"isError": True, "content": [{"type": "text", "text": "denied"}]})

    try:
        service.call_tool(server.id, "get_page", {"url": "https://private.example"})
    except ValueError as exc:
        assert "MCP tool returned an error" in str(exc)
    else:
        raise AssertionError("MCP error result was treated as a success")

    assert service.events(server.id)[0]["ok"] is False


def test_mcp_events_survive_service_restart_without_sensitive_data(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "mcp.json"
    service = McpCenterService(settings_file)
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_call", lambda item, name, arguments: {"content": [{"text": "secret"}]})

    service.call_tool(server.id, "get_page", {"url": "https://private.example"})

    event = McpCenterService(settings_file).events(server.id)[0]
    assert event["tool_name"] == "get_page"
    assert "arguments" not in event and "result" not in event and "error" not in event


def test_mcp_discovered_tools_are_available_after_service_restart(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "mcp.json"
    service = McpCenterService(settings_file)
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_discover", lambda item: ({"name": "get_page", "annotations": {"readOnlyHint": True}},))

    service.discover_tools(server.id)

    assert McpCenterService(settings_file).cached_tools(server.id) == (
        {"name": "get_page", "annotations": {"readOnlyHint": True}},
    )


def test_enabled_tools_uses_cached_definitions_without_starting_mcp_at_boot(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "_discover", lambda item: ({"name": "get_page", "inputSchema": {"type": "object", "properties": {}}},))
    service.discover_tools(server.id)
    restarted = McpCenterService(tmp_path / "mcp.json")
    monkeypatch.setattr(restarted, "discover_tools", lambda server_id: (_ for _ in ()).throw(AssertionError("bootstrap must not discover MCP tools")))

    tools = restarted.enabled_tools(cached_only=True)

    assert [(item.id, definition["name"]) for item, definition in tools] == [(server.id, "get_page")]
