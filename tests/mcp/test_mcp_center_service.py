from pathlib import Path

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
