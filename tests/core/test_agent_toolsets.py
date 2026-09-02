from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.base import Tool
from iris_agent.tools.capabilities import CapabilityResolver
from iris_agent.tools.registry import ToolRegistry


class Provider:
    model = "model"

    def __init__(self):
        self.tools = []

    def complete(self, messages, tools):
        self.tools.append(tools)
        return ProviderResponse(content="done")


def test_agent_resolves_requested_toolsets_for_each_turn(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("recall", "recall", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("write_file", "write", {"type": "object", "properties": {}}, lambda: None))
    resolver = CapabilityResolver(registry, {"safe": ("recall",), "coding": ("write_file",)})
    provider = Provider()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system", capability_resolver=resolver)

    list(service.run(session.id, "one", toolsets=("safe",)))
    list(service.run(session.id, "two", toolsets=("coding",)))

    assert [[schema["function"]["name"] for schema in schemas] for schemas in provider.tools] == [["recall"], ["write_file"]]


def test_interview_collection_request_exposes_only_the_fast_collection_tool(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("collect_interview_knowledge", "fast", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("web_search", "search", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("delegate_tasks", "delegate", {"type": "object", "properties": {}}, lambda: None))
    provider = Provider()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system")

    list(service.run(session.id, "搜索 LLM 面试题并加入知识库"))

    assert [[schema["function"]["name"] for schema in schemas] for schemas in provider.tools] == [["collect_interview_knowledge"]]


def test_direct_interview_page_collection_uses_the_full_collection_tool(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("collect_interview_knowledge", "fast", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("fetch_page", "summary", {"type": "object", "properties": {}}, lambda: None))
    provider = Provider()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system")

    list(service.run(
        session.id,
        "https://notes.example.com/rag_interview.html#_9-rag 抓取这个页面的面试经验",
    ))

    assert [[schema["function"]["name"] for schema in schemas] for schemas in provider.tools] == [["collect_interview_knowledge"]]


def test_ordinary_request_does_not_expose_delegation_tools(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("web_search", "search", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("delegate_tasks", "delegate", {"type": "object", "properties": {}}, lambda: None))
    provider = Provider()
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("test")
    service = AgentService(AgentLoop(provider, registry), repo, "system")

    list(service.run(session.id, "搜索今天的 AI 新闻"))

    assert [[schema["function"]["name"] for schema in schemas] for schemas in provider.tools] == [["web_search"]]
