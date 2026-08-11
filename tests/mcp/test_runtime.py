from pathlib import Path

from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import register_mcp_tools
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
