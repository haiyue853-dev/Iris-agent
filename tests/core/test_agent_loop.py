from iris_agent.core.agent import AgentLoop
from iris_agent.core.models import Message, ProviderResponse, ToolCall
from iris_agent.tools.builtin.time_tool import build_current_time_tool
from iris_agent.tools.registry import ToolRegistry


class FakeProvider:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete(self, messages, tools):
        return self.responses.pop(0)


def test_loop_executes_tool_then_returns_final_text():
    provider = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("call-1", "current_time", {"timezone": "UTC"})]),
        ProviderResponse(content="done"),
    )
    registry = ToolRegistry()
    registry.register(build_current_time_tool())
    events = list(AgentLoop(provider, registry, max_tool_rounds=2).run([Message(role="user", content="time?")]))
    assert [event.type for event in events] == ["react_step", "tool_started", "tool_finished", "react_step", "react_step", "text_delta", "message_completed"]
    assert [event.data["phase"] for event in events if event.type == "react_step"] == ["action", "observation", "final"]


def test_loop_exposes_a_brief_thought_before_tool_actions():
    provider = FakeProvider(
        ProviderResponse(content="I will check the time.", tool_calls=[ToolCall("call-1", "current_time", {})]),
        ProviderResponse(content="done"),
    )
    registry = ToolRegistry()
    registry.register(build_current_time_tool())

    events = list(AgentLoop(provider, registry, max_tool_rounds=2).run([]))

    thought = next(event for event in events if event.type == "react_step" and event.data["phase"] == "thought")
    assert thought.data["content"] == "I will check the time."


def test_loop_emits_error_at_tool_round_limit():
    response = ProviderResponse(tool_calls=[ToolCall("c", "missing", {})])
    events = list(AgentLoop(FakeProvider(response, response), ToolRegistry(), max_tool_rounds=1).run([]))
    assert events[-1].type == "error"
    assert events[-1].data["code"] == "tool_round_limit"


def test_loop_allows_final_text_after_using_last_tool_round():
    response = ProviderResponse(tool_calls=[ToolCall("c", "missing", {})])
    events = list(AgentLoop(FakeProvider(response, ProviderResponse(content="final")), ToolRegistry(), max_tool_rounds=1).run([]))
    assert events[-1].type == "message_completed"


def test_malformed_arguments_do_not_execute_tool():
    calls = []
    registry = ToolRegistry()
    from iris_agent.tools.base import Tool
    registry.register(Tool("safe", "safe", {"type": "object", "properties": {}}, lambda: calls.append(True)))
    malformed = ProviderResponse(tool_calls=[ToolCall("c", "safe", {}, "invalid_tool_arguments")])
    events = list(AgentLoop(FakeProvider(malformed, ProviderResponse(content="handled")), registry, 1).run([]))
    assert calls == []
    assert next(event for event in events if event.type == "tool_finished").data["error_code"] == "invalid_tool_arguments"


def test_loop_feeds_a_failed_observation_back_to_the_next_reasoning_round():
    provider = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("call-1", "missing", {})]),
        ProviderResponse(content="The requested tool is unavailable, so I cannot complete it."),
    )

    events = list(AgentLoop(provider, ToolRegistry(), max_tool_rounds=2).run([]))

    observation = next(event for event in events if event.type == "react_step" and event.data["phase"] == "observation")
    assert observation.data["ok"] is False
    assert observation.data["error_code"] == "unknown_tool"
    assert provider.responses == []


def test_loop_can_retry_a_tool_with_changed_arguments_after_a_failure():
    class Provider:
        def __init__(self):
            self.responses = [
                ProviderResponse(tool_calls=[ToolCall("one", "search", {"query": "python interview"})]),
                ProviderResponse(tool_calls=[ToolCall("two", "search", {"query": "python interview answers"})]),
                ProviderResponse(content="A usable source was found."),
            ]

        def complete(self, messages, tools):
            return self.responses.pop(0)

    calls = []
    registry = ToolRegistry()
    from iris_agent.tools.base import Tool, ToolInvocationError
    def search(query):
        calls.append(query)
        if len(calls) == 1:
            raise ToolInvocationError("source_unavailable", "source unavailable")
        return {"results": ["https://example.test/qa"]}
    registry.register(Tool("search", "search", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, search))

    events = list(AgentLoop(Provider(), registry, max_tool_rounds=3).run([]))

    actions = [event.data for event in events if event.type == "react_step" and event.data["phase"] == "action"]
    assert calls == ["python interview", "python interview answers"]
    assert actions[0]["attempt"] == actions[1]["attempt"] == 1
    assert events[-1].type == "message_completed"


def test_loop_blocks_a_third_identical_tool_call_with_replanning_guidance():
    response = ProviderResponse(tool_calls=[ToolCall("repeat", "missing", {"topic": "python"})])
    events = list(AgentLoop(FakeProvider(response, response, response, ProviderResponse(content="I will change the plan.")), ToolRegistry(), max_tool_rounds=4).run([]))

    blocked = next(event for event in events if event.type == "tool_finished" and event.data.get("error_code") == "repeated_tool_call")
    assert blocked.data["ok"] is False


def test_loop_requests_approval_before_executing_a_write_tool():
    calls = []
    registry = ToolRegistry()
    from iris_agent.tools.base import Tool
    registry.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: calls.append(True), requires_approval=True))
    events = list(AgentLoop(FakeProvider(ProviderResponse(tool_calls=[ToolCall("c", "write", {})])), registry, 1).run([]))
    assert [event.type for event in events] == ["react_step", "tool_started", "tool_approval_requested"]
    assert events[-1].data["name"] == "write"
    assert calls == []
