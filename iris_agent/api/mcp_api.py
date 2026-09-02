from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictBool


class McpCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    transport: str = Field(default="stdio", pattern="^(stdio|http)$")
    command: str = Field(default="", max_length=300)
    url: str = Field(default="", max_length=2000)
    args: list[str] = Field(default_factory=list, max_length=30)
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)


class McpEnabledRequest(BaseModel):
    enabled: StrictBool


class McpAllowedToolsRequest(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)


class McpEnvironmentRequest(BaseModel):
    environment: dict[str, str] = Field(default_factory=dict, max_length=50)


class McpTimeoutRequest(BaseModel):
    timeout_seconds: int = Field(ge=1, le=120)


class McpHeadersRequest(BaseModel):
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)


def _data(server, tools=(), *, connected=False):
    return {"id": server.id, "name": server.name, "transport": server.transport, "command": server.command, "url": server.url, "args": list(server.args), "allowed_tools": list(server.allowed_tools), "env_keys": [key for key, _ in server.environment], "header_keys": [key for key, _ in server.headers], "timeout_seconds": server.timeout_seconds, "enabled": server.enabled, "status": "connected" if connected else "configured", "discovered_tools": list(tools)}


def register_mcp_routes(app, mcp, refresher=None) -> None:
    def refresh():
        if refresher is not None:
            refresher.refresh()

    @app.get("/api/mcp/servers")
    def list_servers():
        return {"servers": [_data(item, mcp.cached_tools(item.id), connected=mcp.is_connected(item.id)) for item in mcp.list()]}

    @app.get("/api/mcp/servers/{server_id}/events")
    def server_events(server_id: str):
        try:
            return {"events": list(mcp.events(server_id))}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "MCP server was not found"}) from exc

    @app.post("/api/mcp/servers", status_code=201)
    def create_server(request: McpCreateRequest):
        try:
            server = mcp.create(name=request.name, command=request.command, args=tuple(request.args), allowed_tools=tuple(request.allowed_tools), transport=request.transport, url=request.url, headers=request.headers)
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

    @app.put("/api/mcp/servers/{server_id}/environment")
    def set_environment(server_id: str, request: McpEnvironmentRequest):
        try:
            server = mcp.set_environment(server_id, request.environment)
            return _data(server)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_validation_error", "message": "环境变量无效"}) from exc

    @app.put("/api/mcp/servers/{server_id}/timeout")
    def set_timeout(server_id: str, request: McpTimeoutRequest):
        try:
            return _data(mcp.set_timeout_seconds(server_id, request.timeout_seconds))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_validation_error", "message": "超时时间无效"}) from exc

    @app.put("/api/mcp/servers/{server_id}/headers")
    def set_headers(server_id: str, request: McpHeadersRequest):
        try:
            return _data(mcp.set_headers(server_id, request.headers))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_validation_error", "message": "请求头无效"}) from exc

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
            tools = mcp.discover_tools(server_id)
            server = mcp.get(server_id)
            return {"tools": list(tools), "server": _data(server, tools, connected=mcp.is_connected(server_id))}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "mcp_server_not_found", "message": "未找到 MCP 服务"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "mcp_discovery_failed", "message": "无法发现 MCP 工具，请先启用并检查命令"}) from exc
