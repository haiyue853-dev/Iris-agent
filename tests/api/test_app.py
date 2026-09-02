from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import Message, ProviderResponse
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


def test_regenerate_stream_replaces_the_previous_turn(tmp_path):
    client = make_client(tmp_path)
    session_id = client.post("/api/sessions", json={"name": "会话"}).json()["id"]
    client.post("/api/chat/stream", json={"session_id": session_id, "message": "第一次"})
    original = client.get(f"/api/sessions/{session_id}").json()["messages"]
    user_id = original[0]["id"]

    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "重新提问", "regenerate_from_message_id": user_id})

    assert response.status_code == 200
    assert '"content": "收到"' in response.text
    assert [item["content"] for item in client.get(f"/api/sessions/{session_id}").json()["messages"] if item["role"] == "user"] == ["重新提问"]


def test_unknown_session_returns_stable_error(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/sessions/missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


def test_validation_uses_stable_error_code(tmp_path):
    secret = "sk-secret-must-not-be-echoed"
    response = make_client(tmp_path).post("/api/sessions", json={"name": {"secret": secret}})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert secret not in response.text


def test_local_ip_frontend_is_allowed_by_cors(tmp_path):
    response = make_client(tmp_path).options(
        "/api/sessions",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_tools_endpoint_lists_registered_tool_metadata(tmp_path):
    sessions = JsonSessionRepository(tmp_path)
    tools = ToolRegistry()
    tools.register(
        Tool(
            "write_note",
            "将内容写入笔记",
            {"type": "object", "properties": {}},
            lambda: "ok",
            requires_approval=True,
        )
    )
    client = TestClient(create_app(AgentService(AgentLoop(EchoProvider(), tools), sessions, "system"), sessions))

    response = client.get("/api/tools")

    assert response.status_code == 200
    assert response.json() == {
        "tools": [
            {
                "name": "write_note",
                "description": "将内容写入笔记",
                "requires_approval": True,
            }
        ]
    }


def test_session_model_profile_round_trip(tmp_path):
    class Profiles:
        def list_state(self):
            return {"profiles": [{"id": "profile-a"}]}

    sessions = JsonSessionRepository(tmp_path)
    client = TestClient(create_app(AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system"), sessions, settings_profiles=Profiles()))
    session_id = client.post("/api/sessions", json={"name": "会话", "model_profile_id": "profile-a"}).json()["id"]
    assert client.get(f"/api/sessions/{session_id}").json()["model_profile_id"] == "profile-a"
    assert client.put(f"/api/sessions/{session_id}/model-profile", json={"model_profile_id": None}).json()["model_profile_id"] is None


def test_session_history_exposes_knowledge_draft_tool_message(tmp_path):
    sessions = JsonSessionRepository(tmp_path)
    session = sessions.create("会话")
    sessions.append(session.id, Message(
        role="tool",
        name="add_knowledge",
        tool_call_id="call-draft",
        content='{"__irisKind":"knowledge-draft","title":"面试题","content":"答案","category":"面经"}',
    ))
    client = TestClient(create_app(AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system"), sessions))

    messages = client.get(f"/api/sessions/{session.id}").json()["messages"]

    assert messages == [{
        "id": messages[0]["id"],
        "role": "tool",
        "content": '{"__irisKind":"knowledge-draft","title":"面试题","content":"答案","category":"面经"}',
        "tool_call_id": "call-draft",
        "name": "add_knowledge",
    }]


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
