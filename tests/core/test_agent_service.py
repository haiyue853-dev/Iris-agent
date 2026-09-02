from iris_agent.core.agent import AgentLoop, AgentService
from types import SimpleNamespace

from iris_agent.core.models import Message, ProviderResponse, ToolCall
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


def test_service_uses_session_model_provider(tmp_path):
    class GlobalProvider:
        model = "global"
        def complete(self, messages, tools):
            return ProviderResponse(content="global")

    class SelectedProvider:
        model = "selected"
        def complete(self, messages, tools):
            return ProviderResponse(content="selected")

    repo = JsonSessionRepository(tmp_path)
    session = repo.create("chat")
    session.model_profile_id = "profile-b"
    repo.save(session)
    service = AgentService(
        AgentLoop(GlobalProvider(), ToolRegistry()), repo, "system",
        model_profile_resolver=lambda profile_id: SelectedProvider() if profile_id == "profile-b" else None,
    )
    events = list(service.run(session.id, "go"))
    assert events[-1].data["metrics"]["model"] == "selected"


def test_service_streams_rag_pipeline_before_model_generation(tmp_path):
    class Knowledge:
        def context_for(self, query, collection_id, mode):
            assert (query, collection_id, mode) == ("RAG 如何工作？", "collection-1", "mix")
            return "[知识库检索结果]\n[1] RAG", [{"index": 1, "routes": ["keyword", "vector", "reranker"]}]

    class AnswerProvider:
        def complete(self, messages, tools):
            return ProviderResponse(content="基于资料回答")

    repo = JsonSessionRepository(tmp_path)
    session = repo.create("rag")
    service = AgentService(
        AgentLoop(AnswerProvider(), ToolRegistry()),
        repo,
        "system",
        knowledge=Knowledge(),
    )

    events = list(service.run(
        session.id,
        "RAG 如何工作？",
        knowledge_collection_id="collection-1",
        knowledge_enabled=True,
    ))

    pipeline = [event.data for event in events if event.type == "pipeline_stage"]
    assert pipeline == [
        {"stage": "planning", "status": "completed", "detail": {"mode": "mix"}},
        {"stage": "retrieval", "status": "running", "detail": {}},
        {"stage": "retrieval", "status": "completed", "detail": {"citations": 1, "routes": ["keyword", "reranker", "vector"]}},
        {"stage": "rerank", "status": "completed", "detail": {"citations": 1}},
        {"stage": "generation", "status": "running", "detail": {}},
    ]
    assert events[-1].type == "message_completed"
    assert repo.get(session.id).messages[-1].citations == [{"index": 1, "routes": ["keyword", "vector", "reranker"]}]


def test_service_adds_grounded_follow_up_suggestions_for_knowledge_citations(tmp_path):
    class Knowledge:
        def context_for(self, query, collection_id, mode):
            return "[知识库检索结果]", [
                {"index": 1, "title": "RAG 分块设计", "routes": ["keyword"]},
                {"index": 2, "title": "RAG 检索设计", "routes": ["vector"]},
            ]

    class AnswerProvider:
        def complete(self, messages, tools):
            return ProviderResponse(content="已根据资料完成回答")

    repo = JsonSessionRepository(tmp_path)
    session = repo.create("rag")
    service = AgentService(AgentLoop(AnswerProvider(), ToolRegistry()), repo, "system", knowledge=Knowledge())

    events = list(service.run(session.id, "RAG 如何工作？", knowledge_enabled=True))

    assert events[-1].data["follow_up_suggestions"] == [
        "请展开说明《RAG 分块设计》中的关键细节。",
        "请展开说明《RAG 检索设计》中的关键细节。",
        "基于这些资料，下一步可以怎么做？",
    ]


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


def test_approved_collaboration_request_unlocks_delegation_tools_for_the_same_turn(tmp_path):
    class CollaborationProvider:
        def __init__(self):
            self.schemas = []
            self.count = 0

        def complete(self, messages, tools):
            self.count += 1
            self.schemas.append([schema["function"]["name"] for schema in tools])
            if self.count == 1:
                return ProviderResponse(tool_calls=[ToolCall("ask-1", "request_subagent_collaboration", {"reason": "任务包含多项独立工作"})])
            return ProviderResponse(content="已完成")

    provider = CollaborationProvider()
    registry = ToolRegistry()
    registry.register(Tool("request_subagent_collaboration", "ask", {"type": "object", "properties": {"reason": {"type": "string"}}}, lambda reason: {"requested": True}, requires_approval=True))
    registry.register(Tool("delegate_tasks", "delegate", {"type": "object", "properties": {}}, lambda: "ok"))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system")

    assert [event.type for event in service.run(session.id, "整理三份不同来源的研究资料")] == ["tool_started", "tool_approval_requested"]
    assert list(service.resolve_tool_approval(session.id, "ask-1", True))[-1].type == "message_completed"
    assert provider.schemas == [["request_subagent_collaboration"], ["delegate_tasks"]]


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


def test_service_forwards_image_attachment_only_when_vision_is_enabled(tmp_path):
    class ImageHandle:
        def read_bytes(self): return b"image-bytes"
        def close(self): pass

    class ImageAttachments:
        def __init__(self): self.downloads = 0
        def read(self, session_id, attachment_id):
            return SimpleNamespace(
                original_name="diagram.png", media_type="image/png", extraction_status="ready", sources=()
            )
        def download_path(self, session_id, attachment_id):
            self.downloads += 1
            return ImageHandle()

    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="解释图片", attachment_ids=["image-1"]))
    attachments = ImageAttachments()
    loop = AgentLoop(Provider(), ToolRegistry())

    disabled = AgentService(loop, repo, "system", attachment_service=attachments, vision_enabled=False)
    assert disabled._build_messages(repo.get(session.id))[-1].image_urls == []
    assert attachments.downloads == 0

    enabled = AgentService(loop, repo, "system", attachment_service=attachments, vision_enabled=True)
    assert enabled._build_messages(repo.get(session.id))[-1].image_urls == ["data:image/png;base64,aW1hZ2UtYnl0ZXM="]
    assert attachments.downloads == 1


def test_regenerate_replaces_the_previous_user_turn_and_its_answer(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")
    list(service.run(session.id, "旧问题"))
    original_user_id = repo.get(session.id).messages[0].id

    list(service.regenerate(session.id, original_user_id, "新问题"))

    saved = repo.get(session.id).messages
    assert [message.content for message in saved if message.role == "user"] == ["新问题"]
    assert len([message for message in saved if message.role == "assistant"]) == 1


def test_regenerate_accepts_a_legacy_client_message_id_by_matching_user_content(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")
    list(service.run(session.id, "抓取热点"))

    list(service.regenerate(session.id, "user-0", "抓取热点"))

    assert [message.content for message in repo.get(session.id).messages if message.role == "user"] == ["抓取热点"]


def test_regenerate_accepts_a_legacy_id_when_the_client_text_was_transformed(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")
    list(service.run(session.id, "抓取热点"))

    list(service.regenerate(session.id, "assistant-1", ""))

    assert [message.content for message in repo.get(session.id).messages if message.role == "user"] == ["抓取热点"]
