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


def test_mcp_server_list_marks_an_open_persistent_session_as_connected(tmp_path, monkeypatch):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    monkeypatch.setattr(mcp, "is_connected", lambda server_id: server_id == server.id)
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).get("/api/mcp/servers")

    assert response.status_code == 200
    assert response.json()["servers"][0]["status"] == "connected"


def test_mcp_discovery_returns_the_connected_server_status(tmp_path, monkeypatch):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=())
    mcp.set_enabled(server.id, True)
    monkeypatch.setattr(mcp, "discover_tools", lambda server_id: ({"name": "get_page"},))
    monkeypatch.setattr(mcp, "is_connected", lambda server_id: server_id == server.id)
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).post(f"/api/mcp/servers/{server.id}/discover")

    assert response.status_code == 200
    assert response.json()["server"]["status"] == "connected"


def test_mcp_environment_endpoint_does_not_return_secret_values(tmp_path):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Search", command="node", args=("server.js",), allowed_tools=())
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).put(f"/api/mcp/servers/{server.id}/environment", json={"environment": {"SEARCH_API_KEY": "top-secret"}})

    assert response.status_code == 200
    assert response.json()["env_keys"] == ["SEARCH_API_KEY"]
    assert "top-secret" not in response.text


def test_mcp_timeout_endpoint_returns_the_saved_timeout(tmp_path):
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Search", command="node", args=("server.js",), allowed_tools=())
    app = FastAPI()
    register_mcp_routes(app, mcp)

    response = TestClient(app).put(f"/api/mcp/servers/{server.id}/timeout", json={"timeout_seconds": 45})

    assert response.status_code == 200
    assert response.json()["timeout_seconds"] == 45
