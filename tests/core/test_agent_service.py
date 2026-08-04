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
