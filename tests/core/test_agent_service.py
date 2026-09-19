from iris_agent.core.agent import AgentLoop, AgentService
from types import SimpleNamespace

import pytest

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


def test_turn_prompt_routes_live_web_requests_to_web_search(tmp_path):
    """提示改为「按检索路由判断」，但对外部/实时信息仍必须指向 web_search，并明令不得声称没有联网工具。"""
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")

    prompt = service._turn_prompt(
        session.id,
        "去百度搜一下热搜前五条输出给我",
        [],
        "fast",
        None,
        "mix",
        False,
        [],
    )

    assert "按「检索路由」判断来源" in prompt
    assert "就调用 web_search" in prompt
    assert "声称自己没有联网工具" in prompt


@pytest.mark.parametrize(
    "text",
    [
        "帮我搜一下 DeepSeek 最新进展",
        "帮我上网查一下",
        "帮我搜索一下下周的天气",
        "查一下最近有什么AI新闻",
        "搜一下今天的新闻",
        "看看今天的热点",
        "联网搜一下",
    ],
)
def test_bare_search_phrasings_are_recognised_as_web_intent(text):
    """回归：这些说法原先一个都不命中。

    旧词表只有 7 个硬编码词（百度|微博|热搜|新闻|热点|联网|外部网站|实时），
    「帮我搜一下X」「帮我上网查一下」这种最常用的表达完全落空，模型拿不到联网提示。
    """
    assert AgentService._is_live_web_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "最近三天提醒我交报告",
        "帮我查找之前的笔记",
        "找一下我之前保存的资料",
        "你好",
        "现在几点",
    ],
)
def test_task_and_local_phrasings_are_not_web_intent(text):
    """时间词归待办解析（parse_chinese_due_at），本地存档归 search_knowledge。

    词表里若收「最近/今天」，像「最近三天提醒我交报告」这种待办就会被误判成要联网。
    """
    assert AgentService._is_live_web_request(text) is False


def test_direct_lookup_path_is_stricter_than_the_hint():
    """直连路径会完全绕开模型，所以要求明确检索动作词，且不碰本地存档与深加工请求。"""
    assert AgentService._is_simple_live_web_lookup("搜一下今天的新闻") is True

    # 指向本地存档：交给模型用 search_knowledge，不能抢答
    assert AgentService._is_simple_live_web_lookup("搜索存档里的RAG资料") is False
    # 深加工请求：留给模型自己拆解
    assert AgentService._is_simple_live_web_lookup("帮我搜一下这个资料的原文并详细分析") is False


def test_turn_prompt_leaves_plain_messages_without_retrieval_directives(tmp_path):
    """没有检索意图的普通消息不该被塞进联网提示。"""
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")

    prompt = service._turn_prompt(session.id, "帮我把这段代码改一下", [], "fast", None, "mix", False, [])

    assert "联网检索要求" not in prompt


def test_build_messages_excludes_messages_marked_hidden_from_model(tmp_path):
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="旧问题"))
    repo.append(session.id, Message(role="assistant", content="错误的历史拒答", context_visible=False))
    repo.append(session.id, Message(role="tool", content='{"error":"web_search_failed"}', context_visible=False))
    repo.append(session.id, Message(role="user", content="新问题"))
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")

    messages = service._build_messages(repo.get(session.id))

    assert [message.content for message in messages if message.role != "system"] == ["旧问题", "新问题"]


def test_build_messages_excludes_legacy_failed_tool_answer_chain(tmp_path):
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="旧问题"))
    call = ToolCall("failed-call", "use_skill", {"skill_id": "web_search"})
    repo.append(session.id, Message(role="assistant", tool_calls=[call]))
    repo.append(session.id, Message(role="tool", content='{"error":"skill_not_found","message":"技能不存在"}', tool_call_id=call.id, name=call.name))
    repo.append(session.id, Message(role="assistant", content="当前没有联网工具"))
    repo.append(session.id, Message(role="user", content="新问题"))
    service = AgentService(AgentLoop(Provider(), ToolRegistry()), repo, "system")

    messages = service._build_messages(repo.get(session.id))

    assert [message.content for message in messages if message.role != "system"] == ["旧问题", "新问题"]


def test_failed_tool_fallback_answer_is_hidden_from_future_context(tmp_path):
    class FailingProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("failed-call", "broken", {})])
            return ProviderResponse(content="工具失败后的兜底回答")

    registry = ToolRegistry()
    registry.register(Tool("broken", "broken", {"type": "object", "properties": {}}, lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(FailingProvider(), registry), repo, "system")

    list(service.run(session.id, "旧问题"))

    saved = repo.get(session.id).messages
    assert saved[-1].content == "工具失败后的兜底回答"
    assert saved[-1].context_visible is False


def test_simple_live_hot_search_uses_direct_fast_path(tmp_path):
    class UnusedProvider:
        def complete(self, messages, tools):
            raise AssertionError("simple live lookup should not require a second model call")

    registry = ToolRegistry()
    registry.register(Tool(
        "web_search",
        "search",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        lambda query: {"results": [{"title": "热搜第一条", "url": "https://example.com/hot", "snippet": "热搜摘要"}]},
    ))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(UnusedProvider(), registry), repo, "system")

    events = list(service.run(session.id, "今天的百度热搜第一是什么"))

    assert [event.type for event in events] == ["tool_started", "tool_finished", "text_delta", "message_completed"]
    assert "热搜第一条" in events[-1].data["content"]


def test_simple_current_time_uses_direct_fast_path(tmp_path):
    class UnusedProvider:
        def complete(self, messages, tools):
            raise AssertionError("simple time lookup should not require a model call")

    registry = ToolRegistry()
    registry.register(Tool(
        "current_time",
        "time",
        {"type": "object", "properties": {}},
        lambda: {"iso": "2026-09-05T20:00:00+08:00"},
    ))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(UnusedProvider(), registry), repo, "system")

    events = list(service.run(session.id, "现在几点"))

    assert [event.type for event in events] == ["tool_started", "tool_finished", "text_delta", "message_completed"]
    assert "2026-09-05T20:00:00+08:00" in events[-1].data["content"]


def test_simple_news_lookup_uses_direct_fast_path(tmp_path):
    class UnusedProvider:
        def complete(self, messages, tools):
            raise AssertionError("simple news lookup should not require a model call")

    registry = ToolRegistry()
    registry.register(Tool(
        "web_search",
        "search",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        lambda query: {"results": [{"title": "美国头条", "url": "https://example.com", "snippet": "新闻摘要"}]},
    ))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(UnusedProvider(), registry), repo, "system")

    events = list(service.run(session.id, "今天美国有什么最大的新闻热点"))

    assert [event.type for event in events] == ["tool_started", "tool_finished", "text_delta", "message_completed"]
    assert "美国头条" in events[-1].data["content"]


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


def test_approved_collaboration_with_existing_delegation_tools_does_not_duplicate(tmp_path):
    class CollaborationProvider:
        def __init__(self):
            self.count = 0

        def complete(self, messages, tools):
            self.count += 1
            if self.count == 1:
                return ProviderResponse(tool_calls=[ToolCall("ask-1", "request_subagent_collaboration", {"reason": "多路搜索"})])
            return ProviderResponse(content="已完成")

    registry = ToolRegistry()
    registry.register(Tool("request_subagent_collaboration", "ask", {"type": "object", "properties": {"reason": {"type": "string"}}}, lambda reason: {"requested": True}, requires_approval=True))
    registry.register(Tool("delegate_workflow", "delegate", {"type": "object", "properties": {}}, lambda: "ok"))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(CollaborationProvider(), registry), repo, "system")

    list(service.run(session.id, "请使用多 Agent / 子代理搜索三类面试资料"))
    events = list(service.resolve_tool_approval(session.id, "ask-1", True))

    assert events[-1].type == "message_completed"


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


def test_rejected_collaboration_stops_without_running_delegation(tmp_path):
    class CollaborationProvider:
        def complete(self, messages, tools):
            return ProviderResponse(tool_calls=[ToolCall("ask-1", "request_subagent_collaboration", {"reason": "多路搜索"})])

    calls = []
    registry = ToolRegistry()
    registry.register(Tool("request_subagent_collaboration", "ask", {"type": "object", "properties": {"reason": {"type": "string"}}}, lambda reason: {"requested": True}, requires_approval=True))
    registry.register(Tool("delegate_workflow", "delegate", {"type": "object", "properties": {}}, lambda: calls.append(True)))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(CollaborationProvider(), registry), repo, "system")

    list(service.run(session.id, "请使用多 Agent 搜索资料"))
    events = list(service.resolve_tool_approval(session.id, "ask-1", False))

    assert calls == []
    assert [event.type for event in events] == ["tool_finished", "text_delta", "message_completed"]
    assert events[-1].data["content"] == "已取消子代理协作。"


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
