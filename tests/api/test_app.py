from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


class EchoProvider:
    def complete(self, messages, tools):
        return ProviderResponse(content="收到")


def make_client(tmp_path):
    sessions = JsonSessionRepository(tmp_path)
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    return TestClient(create_app(service, sessions))


def test_session_and_streaming_chat(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/api/sessions", json={"name": "会话"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "你好"})
    assert response.status_code == 200
    assert '"type": "text_delta"' in response.text
    assert client.get(f"/api/sessions/{session_id}").json()["messages"][-1]["content"] == "收到"


def test_unknown_session_returns_stable_error(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/sessions/missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


def test_validation_uses_stable_error_code(tmp_path):
    response = make_client(tmp_path).post("/api/chat/stream", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


def test_approved_tool_call_resumes_streaming_chat(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                from iris_agent.core.models import ToolCall
                return ProviderResponse(tool_calls=[ToolCall("call-1", "write", {})])
            return ProviderResponse(content="完成")

    sessions = JsonSessionRepository(tmp_path)
    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    client = TestClient(create_app(AgentService(AgentLoop(Provider(), tools), sessions, "system"), sessions))
    session_id = client.post("/api/sessions", json={"name": "会话"}).json()["id"]

    waiting = client.post("/api/chat/stream", json={"session_id": session_id, "message": "执行"})
    assert '"type": "tool_approval_requested"' in waiting.text
    resumed = client.post(f"/api/sessions/{session_id}/tool-approvals/call-1", json={"approved": True})
    assert resumed.status_code == 200
    assert '"type": "tool_finished"' in resumed.text
    assert '"content": "完成"' in resumed.text
