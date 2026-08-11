from iris_agent.mcp_center.service import McpCenterService
from iris_agent.tools.base import Tool, ToolInvocationError
from iris_agent.tools.registry import ToolRegistry


def register_mcp_tools(registry: ToolRegistry, mcp: McpCenterService) -> None:
    for server, definition in mcp.enabled_tools():
        original_name = str(definition["name"])
        schema = dict(definition["inputSchema"])
        name = f"mcp__{server.id}__{original_name}"
        description = str(definition.get("description") or original_name)

        def invoke(*, _server_id=server.id, _tool_name=original_name, **arguments):
            try:
                return mcp.call_tool(_server_id, _tool_name, arguments)
            except ValueError as exc:
                raise ToolInvocationError("mcp_tool_error", str(exc)) from exc

        registry.register(Tool(name, f"MCP {server.name}: {description}", schema, invoke))
