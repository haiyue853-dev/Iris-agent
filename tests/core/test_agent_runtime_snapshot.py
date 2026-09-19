from types import SimpleNamespace

from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


class CapturingProvider:
    model = "test-model"

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.messages = []
        self.tools = []

    def complete(self, messages, tools):
        self.messages.append(list(messages))
        self.tools.append(list(tools))
        return self.responses.pop(0) if self.responses else ProviderResponse(content="done")


class MutableMemory:
    def __init__(self):
        self.value = "first"

    def inject(self):
        return [SimpleNamespace(category="fact", content=self.value)]


def test_runtime_snapshot_refreshes_memory_and_tools(tmp_path):
    provider = CapturingProvider()
    memory = MutableMemory()
    registry = ToolRegistry()
    registry.register(Tool("recall", "recall", {"type": "object", "properties": {}}, lambda: None))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system", memory=memory)

    list(service.run(session.id, "one", response_mode="fast"))
    memory.value = "second"
    registry.register(Tool("later", "later", {"type": "object", "properties": {}}, lambda: None))
    list(service.run(session.id, "two", response_mode="thinking"))

    first_system = [message.content for message in provider.messages[0] if message.role == "system"]
    second_system = [message.content for message in provider.messages[1] if message.role == "system"]
    assert first_system == ["system", "[记忆·fact] first"]
    assert second_system == ["system", "[记忆·fact] second"]
    assert [schema["function"]["name"] for schema in provider.tools[0]] == ["recall"]
    assert [schema["function"]["name"] for schema in provider.tools[1]] == ["recall", "later"]
    saved = repo.get(session.id)
    assert saved.runtime_snapshot is not None
    user_messages = [message for message in saved.messages if message.role == "user"]
    assert "快速模式" in user_messages[0].prompt_content
    assert "思考模式" in user_messages[1].prompt_content


def test_long_lived_session_sees_memory_written_after_it_started(tmp_path):
    """QQ 网关把 (platform, user_id) 永久映射到同一个 session，会话中途写入的记忆必须生效。"""
    provider = CapturingProvider()
    memory = MutableMemory()
    registry = ToolRegistry()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system", memory=memory)

    list(service.run(session.id, "记住我喜欢乌龙茶", response_mode="fast"))
    memory.value = "用户喜欢乌龙茶"
    list(service.run(session.id, "我喜欢什么茶？", response_mode="fast"))

    system_contents = [message.content for message in provider.messages[-1] if message.role == "system"]
    assert system_contents == ["system", "[记忆·fact] 用户喜欢乌龙茶"]
    assert repo.get(session.id).runtime_snapshot.epoch == 2


def test_runtime_snapshot_survives_json_round_trip(tmp_path):
    provider = CapturingProvider()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system")

    list(service.run(session.id, "hello"))
    restored = JsonSessionRepository(tmp_path).get(session.id)

    assert restored.runtime_snapshot.prefix_hash == repo.get(session.id).runtime_snapshot.prefix_hash


def test_approval_resume_keeps_knowledge_context_and_citations(tmp_path):
    provider = CapturingProvider([
        ProviderResponse(tool_calls=[ToolCall("call-1", "write", {})]),
        ProviderResponse(content="done"),
    ])
    registry = ToolRegistry()
    registry.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")

    class Knowledge:
        def context_for(self, query, collection_id, mode):
            return "[知识] 固定上下文", [{"index": 1, "title": "doc"}]

    service = AgentService(AgentLoop(provider, registry), repo, "system", knowledge=Knowledge())

    list(service.run(session.id, "question", knowledge_collection_id="c1", knowledge_enabled=True, response_mode="thinking"))
    events = list(service.resolve_tool_approval(session.id, "call-1", True))

    resumed_user = next(message for message in provider.messages[-1] if message.role == "user")
    assert "[知识] 固定上下文" in resumed_user.model_content
    assert "思考模式" in resumed_user.model_content
    assert events[-1].data["citations"] == [{"index": 1, "title": "doc"}]
