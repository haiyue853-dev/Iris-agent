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
