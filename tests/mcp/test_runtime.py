from pathlib import Path

from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import McpToolRefresher, register_mcp_tools
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def test_registers_only_enabled_allowlisted_mcp_tools_with_namespaces(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    allowed = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    blocked = service.create(name="Other", command="node", args=("other.js",), allowed_tools=("get_page",))
    service.set_enabled(allowed.id, True)

    monkeypatch.setattr(service, "discover_tools", lambda server_id: (
        {"name": "get_page", "description": "Read a page", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
        {"name": "write_page", "inputSchema": {"type": "object", "properties": {}}},
    ))
    calls: list[tuple[str, str, dict[str, object]]] = []
    monkeypatch.setattr(service, "call_tool", lambda server_id, name, arguments: calls.append((server_id, name, arguments)) or {"content": [{"type": "text", "text": "ok"}]})

    registry = ToolRegistry()
    register_mcp_tools(registry, service)
    name = f"mcp__{allowed.id}__get_page"

    assert [item["function"]["name"] for item in registry.schemas()] == [name]
    assert registry.invoke(name, {"url": "https://example.test"}).value == {"content": [{"type": "text", "text": "ok"}]}
    assert calls == [(allowed.id, "get_page", {"url": "https://example.test"})]
    assert blocked.id not in registry.schemas()[0]["function"]["name"]


def test_mcp_tools_require_approval_unless_marked_read_only(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(
        name="Files",
        command="node",
        args=("server.js",),
        allowed_tools=("read_file", "write_file"),
    )
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "discover_tools", lambda server_id: (
        {"name": "read_file", "inputSchema": {"type": "object", "properties": {}}, "annotations": {"readOnlyHint": True}},
        {"name": "write_file", "inputSchema": {"type": "object", "properties": {}}},
    ))

    registry = ToolRegistry()
    register_mcp_tools(registry, service)

    assert not registry.requires_approval(f"mcp__{server.id}__read_file")
    assert registry.requires_approval(f"mcp__{server.id}__write_file")


def test_refresh_replaces_only_mcp_tools_and_keeps_builtin_tools(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "discover_tools", lambda server_id: (
        {"name": "get_page", "inputSchema": {"type": "object", "properties": {}}},
    ))
    registry = ToolRegistry()
    registry.register(Tool("current_time", "time", {"type": "object", "properties": {}}, lambda: "now"))
    registry.register(Tool("mcp__old__stale", "stale", {"type": "object", "properties": {}}, lambda: None))

    McpToolRefresher(registry, service).refresh()

    names = [item["function"]["name"] for item in registry.schemas()]
    assert "current_time" in names
    assert f"mcp__{server.id}__get_page" in names
    assert "mcp__old__stale" not in names


def test_refresh_discovers_each_enabled_server_only_once(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    calls: list[str] = []

    def discover(server_id: str):
        calls.append(server_id)
        return ({"name": "get_page", "inputSchema": {"type": "object", "properties": {}}},)

    monkeypatch.setattr(service, "discover_tools", discover)
    registry = ToolRegistry()

    McpToolRefresher(registry, service).refresh()

    assert calls == [server.id]
    assert f"mcp__{server.id}__get_page" in [item["function"]["name"] for item in registry.schemas()]


def test_refresh_keeps_existing_mcp_tools_when_an_enabled_server_cannot_be_discovered(tmp_path: Path, monkeypatch) -> None:
    service = McpCenterService(tmp_path / "mcp.json")
    server = service.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page",))
    service.set_enabled(server.id, True)
    monkeypatch.setattr(service, "discover_tools", lambda server_id: (_ for _ in ()).throw(ValueError("offline")))
    registry = ToolRegistry()
    registry.register(Tool("mcp__old__get_page", "old", {"type": "object", "properties": {}}, lambda: None))

    try:
        McpToolRefresher(registry, service).refresh()
    except ValueError:
        pass
    else:
        raise AssertionError("refresh should report discovery failure")

    assert [item["function"]["name"] for item in registry.schemas()] == ["mcp__old__get_page"]
