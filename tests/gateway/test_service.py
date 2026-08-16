from iris_agent.core.models import AgentEvent
from iris_agent.gateway.base import InboundMessage
from iris_agent.gateway.service import GatewayService
from iris_agent.sessions.json_store import JsonSessionRepository


class FakeAgent:
    """Mimic AgentService: content arrives via ``text_delta``; ``message_completed`` is stripped."""

    def __init__(self, reply: str = "ok"):
        self.reply = reply
        self.runs: list[tuple] = []

    def run(self, session_id: str, text: str):
        self.runs.append(("run", session_id, text))
        yield AgentEvent("text_delta", {"content": self.reply})
        yield AgentEvent("message_completed", {"message_id": "m1"})

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool):
        self.runs.append(("resolve", session_id, call_id, approved))
        yield AgentEvent("text_delta", {"content": f"拒绝结果({approved})"})
        yield AgentEvent("message_completed", {"message_id": "m2"})


class ApprovalAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        self.runs.append(("run", session_id, text))
        yield AgentEvent("tool_approval_requested", {"call_id": "c1", "name": "some_tool"})


def _service(tmp_path, agent=None, **kwargs) -> GatewayService:
    sessions = JsonSessionRepository(tmp_path / "sessions")
    return GatewayService(agent or FakeAgent(), sessions, **kwargs)


def test_handle_returns_reply_and_creates_session(tmp_path):
    service = _service(tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "你好"))

    assert reply == "ok"
    session_id = service.session_id("qq", "123")
    assert session_id.startswith("session_")


def test_same_user_reuses_session(tmp_path):
    agent = FakeAgent()
    service = _service(tmp_path, agent)

    service.handle(InboundMessage("qq", "123", "a"))
    service.handle(InboundMessage("qq", "123", "b"))

    assert agent.runs[0][1] == agent.runs[1][1]


def test_different_users_get_different_sessions(tmp_path):
    agent = FakeAgent()
    service = _service(tmp_path, agent)

    service.handle(InboundMessage("qq", "111", "a"))
    service.handle(InboundMessage("qq", "222", "b"))

    assert agent.runs[0][1] != agent.runs[1][1]


def test_blank_text_returns_empty(tmp_path):
    agent = FakeAgent()
    service = _service(tmp_path, agent)

    reply = service.handle(InboundMessage("qq", "123", "   "))

    assert reply == ""
    assert agent.runs == []


def test_state_persists_across_instances(tmp_path):
    state_file = tmp_path / "gateway" / "sessions.json"
    first = _service(tmp_path, state_file=state_file)
    first.handle(InboundMessage("qq", "123", "a"))
    expected = first.session_id("qq", "123")

    second = _service(tmp_path, state_file=state_file)

    assert second.session_id("qq", "123") == expected


def test_approval_request_is_refused(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)

    reply = service.handle(InboundMessage("qq", "123", "触发审批"))

    assert reply == "拒绝结果(False)"
    assert agent.runs[1] == ("resolve", agent.runs[0][1], "c1", False)


class ChunkedAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        yield AgentEvent("text_delta", {"content": "第一段"})
        yield AgentEvent("text_delta", {"content": "第二段"})
        yield AgentEvent("message_completed", {"message_id": "m1"})


def test_accumulates_multiple_text_deltas(tmp_path):
    service = _service(tmp_path, ChunkedAgent())

    reply = service.handle(InboundMessage("qq", "123", "hi"))

    assert reply == "第一段第二段"


class LegacyAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        yield AgentEvent("message_completed", {"content": "旧版内容"})


def test_falls_back_to_message_completed_content(tmp_path):
    service = _service(tmp_path, LegacyAgent())

    reply = service.handle(InboundMessage("qq", "123", "hi"))

    assert reply == "旧版内容"
