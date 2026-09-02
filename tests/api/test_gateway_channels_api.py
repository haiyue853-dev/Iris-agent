from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry
from iris_agent.gateway.napcat import NapCatLauncher


class EchoProvider:
    def complete(self, messages, tools):
        return ProviderResponse(content="ok")


class FakeQQAdapter:
    def __init__(self, connected: bool):
        self.connected = connected
        self.sent: list[tuple[str, str]] = []

    def push_text(self, user_id: str, text: str) -> bool:
        if not self.connected:
            return False
        self.sent.append((user_id, text))
        return True


def make_client(tmp_path, adapter=None):
    sessions = JsonSessionRepository(tmp_path)
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    return TestClient(create_app(service, sessions, qq_adapter=adapter, qq_ws_path="/gateway/qq/ws"))


def test_lists_qq_channel_connection_status(tmp_path):
    response = make_client(tmp_path, FakeQQAdapter(connected=True)).get("/api/gateway/channels")

    assert response.status_code == 200
    assert response.json() == {
        "channels": [{
            "id": "qq",
            "name": "QQ",
            "enabled": True,
            "connected": True,
            "transport": "OneBot 11 反向 WebSocket",
            "websocket_path": "/gateway/qq/ws",
        }]
    }


def test_reports_disabled_qq_channel(tmp_path):
    channel = make_client(tmp_path).get("/api/gateway/channels").json()["channels"][0]

    assert channel["enabled"] is False
    assert channel["connected"] is False


def test_sends_qq_test_message(tmp_path):
    adapter = FakeQQAdapter(connected=True)
    response = make_client(tmp_path, adapter).post(
        "/api/gateway/qq/test",
        json={"user_id": "123456", "text": "Iris QQ 连接测试"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert adapter.sent == [("123456", "Iris QQ 连接测试")]


def test_rejects_test_message_when_qq_is_not_connected(tmp_path):
    response = make_client(tmp_path, FakeQQAdapter(connected=False)).post(
        "/api/gateway/qq/test",
        json={"user_id": "123456", "text": "test"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "qq_not_connected"


def test_napcat_path_can_be_saved_and_read(tmp_path):
    executable = tmp_path / "NapCat.Shell.exe"
    executable.write_text("stub", encoding="utf-8")
    launcher = NapCatLauncher(tmp_path / "napcat.json")
    client = TestClient(create_app(AgentService(AgentLoop(EchoProvider(), ToolRegistry()), JsonSessionRepository(tmp_path / "sessions"), "system"), JsonSessionRepository(tmp_path / "sessions2"), napcat=launcher))

    response = client.put("/api/gateway/napcat", json={"path": str(executable)})
    assert response.status_code == 200
    assert response.json()["path"] == str(executable)
    assert client.get("/api/gateway/napcat").json()["configured"] is True


def test_napcat_rejects_relative_path(tmp_path):
    launcher = NapCatLauncher(tmp_path / "napcat.json")
    sessions = JsonSessionRepository(tmp_path / "sessions")
    client = TestClient(create_app(AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system"), sessions, napcat=launcher))

    response = client.put("/api/gateway/napcat", json={"path": "NapCat.exe"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "napcat_path_must_be_absolute"
