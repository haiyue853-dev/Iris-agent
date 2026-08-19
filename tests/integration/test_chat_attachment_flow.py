from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.service import AttachmentService
from iris_agent.attachments.storage import AttachmentStorage
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class CapturingProvider:
    def __init__(self):
        self.messages = []

    def complete(self, messages, tools):
        self.messages.append((messages, tools))
        return ProviderResponse(content="done")


def test_chat_context_shows_attachment_and_read_tool(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("chat")
    attachments = AttachmentService(AttachmentStorage(tmp_path / "files", 10000, 10000, 5), sessions, LocalAttachmentExtractor(1000))
    item = attachments.upload(session.id, "brief.txt", b"context", "text/plain")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system", attachment_service=attachments)

    list(service.run(session.id, "总结这个文件", [item.id]))

    messages, schemas = provider.messages[0]
    assert "brief.txt" in messages[-1].content
    assert item.id in messages[-1].content
    assert "read_attachment" in messages[-1].content
    assert any(schema["function"]["name"] == "read_attachment" for schema in schemas)


def test_provider_can_read_current_message_attachment_by_context_id(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("chat")
    attachments = AttachmentService(AttachmentStorage(tmp_path / "files", 10000, 10000, 5), sessions, LocalAttachmentExtractor(1000))
    item = attachments.upload(session.id, "brief.txt", b"context", "text/plain")

    class Provider:
        def __init__(self): self.calls = 0
        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                assert item.id in messages[-1].content
                return ProviderResponse(tool_calls=[ToolCall("read-1", "read_attachment", {"attachment_id": item.id})])
            return ProviderResponse(content="done")

    service = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system", attachment_service=attachments)
    events = list(service.run(session.id, "总结这个文件", [item.id]))
    finished = next(event for event in events if event.type == "tool_finished")
    assert finished.data["result"]["text"] == "context"


def test_uploaded_attachment_flows_from_provider_tool_read_to_sourced_reply(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("chat")
    attachments = AttachmentService(
        AttachmentStorage(tmp_path / "files", 10000, 10000, 5),
        sessions,
        LocalAttachmentExtractor(1000),
    )
    item = attachments.upload(session.id, "brief.txt", b"attachment context", "text/plain")

    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("read-1", "read_attachment", {"attachment_id": item.id})])
            assert '"text": "attachment context"' in messages[-1].content
            assert '"sources": ["brief.txt"]' in messages[-1].content
            return ProviderResponse(content="根据来源 brief.txt：attachment context")

    service = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system", attachment_service=attachments)
    events = list(service.run(session.id, "总结这个文件", [item.id]))

    assert next(event for event in events if event.type == "tool_finished").data["result"]["sources"] == ["brief.txt"]
    assert next(event for event in events if event.type == "message_completed").data == {"message_id": sessions.get(session.id).messages[-1].id}
    assert sessions.get(session.id).messages[-1].content == "根据来源 brief.txt：attachment context"
