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
