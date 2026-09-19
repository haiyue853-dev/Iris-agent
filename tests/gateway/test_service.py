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

    assert reply.text == "ok"
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

    assert reply.text == ""
    assert reply.files == []
    assert agent.runs == []


def test_state_persists_across_instances(tmp_path):
    state_file = tmp_path / "gateway" / "sessions.json"
    first = _service(tmp_path, state_file=state_file)
    first.handle(InboundMessage("qq", "123", "a"))
    expected = first.session_id("qq", "123")

    second = _service(tmp_path, state_file=state_file)

    assert second.session_id("qq", "123") == expected


def test_approval_request_waits_for_qq_confirmation(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)

    reply = service.handle(InboundMessage("qq", "123", "触发审批"))

    assert "待确认操作【A-001】" in reply.text
    assert "some_tool" in reply.text
    assert "确认 A-001" in reply.text
    assert len(agent.runs) == 1


def test_qq_confirmation_resumes_the_pending_tool(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)
    service.handle(InboundMessage("qq", "123", "触发审批"))

    reply = service.handle(InboundMessage("qq", "123", "确认 A-001"))

    assert reply.text == "拒绝结果(True)"
    assert agent.runs[1] == ("resolve", agent.runs[0][1], "c1", True)


def test_qq_cancellation_rejects_the_pending_tool(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)
    service.handle(InboundMessage("qq", "123", "触发审批"))

    reply = service.handle(InboundMessage("qq", "123", "取消 A-001"))

    assert "已取消待确认操作【A-001】" in reply.text
    assert agent.runs[1] == ("resolve", agent.runs[0][1], "c1", False)


def test_unrelated_message_does_not_bypass_a_pending_confirmation(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)
    service.handle(InboundMessage("qq", "123", "触发审批"))

    reply = service.handle(InboundMessage("qq", "123", "换个话题"))

    assert "A-001" in reply.text
    assert "确认" in reply.text
    assert len(agent.runs) == 1


def test_another_user_cannot_confirm_someone_elses_operation(tmp_path):
    agent = ApprovalAgent()
    service = _service(tmp_path, agent)
    service.handle(InboundMessage("qq", "123", "触发审批"))

    reply = service.handle(InboundMessage("qq", "456", "确认 A-001"))

    assert "没有找到属于你的待确认操作" in reply.text
    assert len(agent.runs) == 1


class ApprovalAgentWithCall(ApprovalAgent):
    """ApprovalAgent that reports the real tool name and arguments under review."""

    def __init__(self, name: str, arguments: dict | None):
        super().__init__()
        self._name = name
        self._arguments = arguments

    def run(self, session_id: str, text: str):
        self.runs.append(("run", session_id, text))
        yield AgentEvent(
            "tool_approval_requested",
            {"call_id": "c1", "name": self._name, "arguments": self._arguments},
        )


def test_gateway_requires_confirmation_for_write_to_ordinary_path(tmp_path):
    agent = ApprovalAgentWithCall("write_file", {"path": "notes/todo.md"})
    service = _service(tmp_path, agent, workspace_root=tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "记一下"))

    assert "notes/todo.md" in reply.text
    assert len(agent.runs) == 1


def test_gateway_requires_confirmation_for_write_that_changes_agent_config(tmp_path):
    agent = ApprovalAgentWithCall("write_file", {"path": "agent.yaml"})
    service = _service(tmp_path, agent, workspace_root=tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "改一下配置"))

    assert "agent.yaml" in reply.text
    assert len(agent.runs) == 1


def test_gateway_requires_confirmation_for_write_that_changes_agent_code(tmp_path):
    agent = ApprovalAgentWithCall("replace_in_file", {"path": "iris_agent/core/agent.py"})
    service = _service(tmp_path, agent, workspace_root=tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "改代码"))

    assert "iris_agent/core/agent.py" in reply.text
    assert len(agent.runs) == 1


def test_gateway_requires_confirmation_for_run_command(tmp_path):
    agent = ApprovalAgentWithCall("run_command", {"command": "git status"})
    service = _service(tmp_path, agent, workspace_root=tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "跑个命令"))

    assert "git status" in reply.text
    assert len(agent.runs) == 1


def test_gateway_confirmation_does_not_depend_on_workspace_root(tmp_path):
    agent = ApprovalAgentWithCall("write_file", {"path": "notes/todo.md"})
    service = _service(tmp_path, agent)

    reply = service.handle(InboundMessage("qq", "123", "记一下"))

    assert "待确认操作【A-001】" in reply.text
    assert len(agent.runs) == 1


class ChunkedAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        yield AgentEvent("text_delta", {"content": "第一段"})
        yield AgentEvent("text_delta", {"content": "第二段"})
        yield AgentEvent("message_completed", {"message_id": "m1"})


def test_accumulates_multiple_text_deltas(tmp_path):
    service = _service(tmp_path, ChunkedAgent())

    reply = service.handle(InboundMessage("qq", "123", "hi"))

    assert reply.text == "第一段第二段"


class LegacyAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        yield AgentEvent("message_completed", {"content": "旧版内容"})


def test_falls_back_to_message_completed_content(tmp_path):
    service = _service(tmp_path, LegacyAgent())

    reply = service.handle(InboundMessage("qq", "123", "hi"))

    assert reply.text == "旧版内容"


class FileMarkerAgent(FakeAgent):
    def run(self, session_id: str, text: str):
        yield AgentEvent("text_delta", {"content": "好的，文件发给你。\n[FILE:D:/agent/iris-agent/日报-2026-08-16.md]\n[FILE:D:\\agent\\iris-agent\\报告.docx]"})
        yield AgentEvent("message_completed", {"message_id": "m1"})


def test_extracts_file_markers_into_files_and_cleans_text(tmp_path):
    service = _service(tmp_path, FileMarkerAgent())

    reply = service.handle(InboundMessage("qq", "123", "把日报发给我"))

    assert reply.files == ["D:/agent/iris-agent/日报-2026-08-16.md", "D:\\agent\\iris-agent\\报告.docx"]
    assert "[FILE:" not in reply.text
    assert reply.text.strip() == "好的，文件发给你。"


def test_no_file_marker_yields_empty_files(tmp_path):
    service = _service(tmp_path)

    reply = service.handle(InboundMessage("qq", "123", "hi"))

    assert reply.files == []
    assert reply.text == "ok"


class FakePersonalAssistant:
    def __init__(self, outcome):
        self.outcome = outcome
        self.messages = []

    def ingest(self, message):
        self.messages.append(message)
        return self.outcome


def test_personal_assistant_receipt_is_prepended_to_agent_reply(tmp_path):
    from iris_agent.personal_assistant.models import IngestOutcome

    personal = FakePersonalAssistant(IngestOutcome(receipt="已存档：资料"))
    service = _service(tmp_path, personal_assistant=personal)

    reply = service.handle(InboundMessage("qq", "123", "资料", raw={"message_id": 1}))

    assert reply.text == "已存档：资料\n\nok"
    assert len(personal.messages) == 1


def test_wecom_messages_also_use_personal_assistant_archive_pipeline(tmp_path):
    from iris_agent.personal_assistant.models import IngestOutcome

    personal = FakePersonalAssistant(IngestOutcome(receipt="已存档：企业微信资料"))
    service = _service(tmp_path, personal_assistant=personal)

    reply = service.handle(InboundMessage("wecom", "owner", "资料", raw={"message_id": "wx-1"}))

    assert reply.text == "已存档：企业微信资料\n\nok"
    assert personal.messages[0].platform == "wecom"


def test_personal_assistant_can_handle_command_without_running_agent(tmp_path):
    from iris_agent.personal_assistant.models import IngestOutcome

    agent = FakeAgent()
    personal = FakePersonalAssistant(IngestOutcome(reply_override="已完成【T-001】"))
    service = _service(tmp_path, agent, personal_assistant=personal)

    reply = service.handle(InboundMessage("qq", "123", "完成 T-001", raw={"message_id": 2}))

    assert reply.text == "已完成【T-001】"
    assert agent.runs == []


def test_duplicate_personal_message_does_not_run_agent_again(tmp_path):
    from iris_agent.personal_assistant.models import IngestOutcome

    agent = FakeAgent()
    personal = FakePersonalAssistant(IngestOutcome(duplicate=True, reply_override=""))
    service = _service(tmp_path, agent, personal_assistant=personal)

    reply = service.handle(InboundMessage("qq", "123", "重复", raw={"message_id": 3}))

    assert reply.text == ""
    assert agent.runs == []
