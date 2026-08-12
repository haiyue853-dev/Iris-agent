from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictBool


class McpCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    command: str = Field(min_length=1, max_length=300)
    args: list[str] = Field(default_factory=list, max_length=30)
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)


class McpEnabledRequest(BaseModel):
    enabled: StrictBool


class McpAllowedToolsRequest(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)


def _data(server):
    return {"id": server.id, "name": server.name, "command": server.command, "args": list(server.args), "allowed_tools": list(server.allowed_tools), "enabled": server.enabled, "status": "configured"}


def register_mcp_routes(app, mcp, refresher=None) -> None:
    def refresh():
        if refresher is not None:
            refresher.refresh()

    @app.get("/api/mcp/servers")
    def list_servers():
        return {"servers": [_data(item) for item in mcp.list()]}

    @app.get("/api/mcp/servers/{server_id}/events")
    def server_events(server_id: str):
        try:
            return {"events": list(mcp.events(server_id))}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "MCP server was not found"}) from exc

    @app.post("/api/mcp/servers", status_code=201)
    def create_server(request: McpCreateRequest):
        try:
            server = mcp.create(name=request.name, command=request.command, args=tuple(request.args), allowed_tools=tuple(request.allowed_tools))
            refresh()
            return _data(server)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_validation_error", "message": "MCP 服务配置无效"}) from exc

    @app.put("/api/mcp/servers/{server_id}/enabled")
    def set_enabled(server_id: str, request: McpEnabledRequest):
        try:
            server = mcp.set_enabled(server_id, request.enabled)
            refresh()
            return _data(server)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc

    @app.put("/api/mcp/servers/{server_id}/allowed-tools")
    def set_allowed_tools(server_id: str, request: McpAllowedToolsRequest):
        try:
            server = mcp.set_allowed_tools(server_id, tuple(request.allowed_tools))
            refresh()
            return _data(server)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_validation_error", "message": "工具白名单无效"}) from exc

    @app.delete("/api/mcp/servers/{server_id}", status_code=204)
    def delete_server(server_id: str):
        try:
            mcp.delete(server_id)
            refresh()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "MCP server was not found"}) from exc

    @app.post("/api/mcp/servers/{server_id}/discover")
    def discover_tools(server_id: str):
        try:
            return {"tools": list(mcp.discover_tools(server_id))}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_discovery_failed", "message": "无法发现 MCP 工具，请先启用并检查命令"}) from exc
