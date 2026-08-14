from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.memory.json_provider import JsonMemoryProvider
from iris_agent.memory.service import MemoryService
from iris_agent.memory.tools import build_memory_tools
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def test_memory_searches_global_and_session_items(tmp_path):
    provider = JsonMemoryProvider(tmp_path / "memories.json")
    service = MemoryService(provider)
    service.remember("Python interview preparation", tags=("python",))
    service.remember("Use short answers", session_id="session_1")

    assert [item.content for item in service.search("Python", "session_1")] == ["Python interview preparation"]
    assert [item.content for item in service.search("short", "session_1")] == ["Use short answers"]
    assert service.search("short", "session_2") == []


def test_agent_injects_only_relevant_memory(tmp_path):
    class Provider:
        def __init__(self): self.messages = []
        def complete(self, messages, tools): self.messages = messages; return ProviderResponse(content="done")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("memory")
    memory = MemoryService(JsonMemoryProvider(tmp_path / "memory.json"))
    memory.remember("Python interview preparation")
    provider = Provider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system", memory=memory)

    list(service.run(session.id, "Python"))

    assert "Relevant saved memories" in provider.messages[-1].content
    assert [message.content for message in sessions.get(session.id).messages] == ["Python", "done"]


def test_memory_write_tool_requires_approval(tmp_path):
    memory = MemoryService(JsonMemoryProvider(tmp_path / "memory.json"))
    search, save = build_memory_tools(memory)

    assert save.requires_approval
    assert save.invoke({"content": "Remember this"}).ok
    assert search.invoke({"query": "Remember"}).value[0]["content"] == "Remember this"
