import pytest

from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.subagents.repository import JsonSubagentRepository
from iris_agent.subagents.service import SubagentService
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def test_subagent_uses_isolated_session_and_tool_allowlist(tmp_path):
    class Provider:
        def __init__(self): self.schemas = []; self.calls = 0
        def complete(self, messages, tools):
            self.schemas = tools
            self.calls += 1
            return ProviderResponse(tool_calls=[ToolCall("safe-call", "safe", {})]) if self.calls == 1 else ProviderResponse(content="isolated result")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    parent = sessions.create("parent")
    provider = Provider()
    tools = ToolRegistry()
    tools.register(Tool("safe", "safe", {"type": "object", "properties": {}}, lambda: "ok"))
    tools.register(Tool("blocked", "blocked", {"type": "object", "properties": {}}, lambda: "no"))
    service = SubagentService(JsonSubagentRepository(tmp_path / "subagents"), AgentService(AgentLoop(provider, tools), sessions, "system"))
    task = service.create(parent.id, "research", "do research", ["safe"])

    completed, _ = service.run(task.id)

    assert completed.status == "completed"
    assert completed.result == "isolated result"
    assert completed.session_id != parent.id
    assert [schema["function"]["name"] for schema in provider.schemas] == ["safe"]
    assert sessions.get(parent.id).messages == []


def test_subagent_recovers_approval_and_enforces_concurrency_limit(tmp_path):
    class WaitingProvider:
        def complete(self, messages, tools):
            return ProviderResponse(tool_calls=[ToolCall("write-call", "write", {})])

    class ResumedProvider:
        def complete(self, messages, tools):
            return ProviderResponse(content="saved")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    parent = sessions.create("parent")
    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    repository = JsonSubagentRepository(tmp_path / "subagents")
    first = SubagentService(repository, AgentService(AgentLoop(WaitingProvider(), tools), sessions, "system"), max_concurrent=1)
    waiting = first.create(parent.id, "save", "save it", ["write"])
    first.run(waiting.id)
    blocked = first.create(parent.id, "other", "do other work", ["write"])

    with pytest.raises(ValueError, match="concurrency"):
        first.run(blocked.id)

    restarted = SubagentService(repository, AgentService(AgentLoop(ResumedProvider(), tools), sessions, "system"), max_concurrent=1)
    completed, _ = restarted.resolve_approval(waiting.id, True)

    assert completed.status == "completed"
    assert completed.result == "saved"
