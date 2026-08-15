from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class CapturingProvider:
    def __init__(self):
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(list(messages))
        return ProviderResponse(content="done")


def test_agent_injects_memory_into_system_messages(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    memory.add("用户偏好中文", "preference")
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", memory=memory)

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system", "[记忆·preference] 用户偏好中文"]


def test_agent_injects_no_memory_when_ledger_empty(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", memory=memory)

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system"]


def test_agent_without_memory_service_behaves_unchanged(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system")

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system"]
