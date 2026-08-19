from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def __init__(self):
        self.count = 0
    def complete(self, messages, tools):
        self.count += 1
        return ProviderResponse(tool_calls=[ToolCall("c1", "echo", {"value": "x"})]) if self.count == 1 else ProviderResponse(content="done")


def test_service_persists_tool_messages_before_completion(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("echo", "echo", {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}, lambda value: value))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    events = list(AgentService(AgentLoop(Provider(), registry), repo, "system").run(session.id, "go"))
    saved = repo.get(session.id).messages
    assert [message.role for message in saved] == ["user", "assistant", "tool", "assistant"]
    assert events[-1].type == "message_completed"
    assert "message_id" in events[-1].data


def test_service_resumes_after_approved_tool_call(tmp_path):
    class ApprovalProvider:
        def __init__(self):
            self.count = 0

        def complete(self, messages, tools):
            self.count += 1
            if self.count == 1:
                return ProviderResponse(tool_calls=[ToolCall("c1", "write", {"value": "x"})])
            return ProviderResponse(content="done")

    registry = ToolRegistry()
    registry.register(Tool("write", "write", {"type": "object", "properties": {"value": {"type": "string"}}}, lambda value: value, requires_approval=True))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(ApprovalProvider(), registry), repo, "system")

    assert [event.type for event in service.run(session.id, "go")] == ["tool_started", "tool_approval_requested"]
    assert [event.type for event in service.resolve_tool_approval(session.id, "c1", True)] == ["tool_finished", "text_delta", "message_completed"]
    assert [message.role for message in repo.get(session.id).messages] == ["user", "assistant", "tool", "assistant"]


def test_service_does_not_execute_rejected_tool_call(tmp_path):
    class ApprovalProvider:
        def __init__(self):
            self.count = 0

        def complete(self, messages, tools):
            self.count += 1
            return ProviderResponse(tool_calls=[ToolCall("c1", "write", {})]) if self.count == 1 else ProviderResponse(content="done")

    calls = []
    registry = ToolRegistry()
    registry.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: calls.append(True), requires_approval=True))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(ApprovalProvider(), registry), repo, "system")

    list(service.run(session.id, "go"))
    events = list(service.resolve_tool_approval(session.id, "c1", False))
    assert calls == []
    assert events[0].data["error_code"] == "tool_approval_rejected"


def test_approved_request_reuses_its_original_scoped_registry(tmp_path):
    from iris_agent.attachments.extraction import LocalAttachmentExtractor
    from iris_agent.attachments.service import AttachmentService
    from iris_agent.attachments.storage import AttachmentStorage

    class ApprovalProvider:
        def __init__(self): self.count = 0
        def complete(self, messages, tools):
            self.count += 1
            if self.count == 1:
                return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {})])
            if self.count == 2:
                return ProviderResponse(tool_calls=[ToolCall("read-1", "read_attachment", {"attachment_id": attachment.id})])
            return ProviderResponse(content="done")

    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    original = AttachmentService(AttachmentStorage(tmp_path / "original", 10000, 10000, 5), repo, LocalAttachmentExtractor(1000))
    attachment = original.upload(session.id, "notes.txt", b"original", "text/plain")
    registry = ToolRegistry()
    registry.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    service = AgentService(AgentLoop(ApprovalProvider(), registry), repo, "system", attachment_service=original)

    list(service.run(session.id, "read", [attachment.id]))
    replacement = AttachmentService(AttachmentStorage(tmp_path / "replacement", 10000, 10000, 5), repo, LocalAttachmentExtractor(1000))
    service.attachment_service = replacement
    events = list(service.resolve_tool_approval(session.id, "write-1", True))

    read_event = next(event for event in events if event.type == "tool_finished" and event.data["name"] == "read_attachment")
    assert read_event.data["result"]["text"] == "original"
