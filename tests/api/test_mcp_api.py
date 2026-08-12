from fastapi import FastAPI
from fastapi.testclient import TestClient

from iris_agent.api.mcp_api import register_mcp_routes
from iris_agent.mcp_center.service import McpCenterService


class Refresher:
    def __init__(self):
        self.calls = 0

    def refresh(self):
        self.calls += 1


def test_updating_an_mcp_allowlist_refreshes_runtime_tools(tmp_path):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    refresher = Refresher()
    app = FastAPI()
    register_mcp_routes(app, mcp, refresher)

    response = TestClient(app).put(f"/api/mcp/servers/{server.id}/allowed-tools", json={"allowed_tools": ["get_page"]})

    assert response.status_code == 200
    assert refresher.calls == 1


def test_mcp_events_endpoint_returns_safe_server_events(tmp_path):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).get(f"/api/mcp/servers/{server.id}/events")

    assert response.status_code == 200
    assert response.json() == {"events": []}


def test_mcp_server_list_includes_cached_discovered_tools(tmp_path, monkeypatch):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    mcp.set_enabled(server.id, True)
    monkeypatch.setattr(mcp, "_discover", lambda item: ({"name": "get_page"},))
    mcp.discover_tools(server.id)
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).get("/api/mcp/servers")

    assert response.status_code == 200
    assert response.json()["servers"][0]["discovered_tools"] == [{"name": "get_page"}]
