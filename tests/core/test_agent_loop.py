from iris_agent.core.agent import AgentLoop
from iris_agent.core.agent_loop import AgentLoop as CompatibleAgentLoop
from iris_agent.core.models import Message, ProviderResponse, ToolCall
from iris_agent.tools.builtin.time_tool import build_current_time_tool
from iris_agent.tools.registry import ToolRegistry
from iris_agent.providers.switchable import SwitchableProvider
from iris_agent.tools.base import Tool
import threading
import time


def test_agent_loop_compatibility_module_exports_same_class():
    assert CompatibleAgentLoop is AgentLoop


class FakeProvider:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete(self, messages, tools):
        return self.responses.pop(0)


class StreamingProvider:
    def stream(self, messages, tools):
        yield ProviderResponse(content="第一段")
        yield ProviderResponse(content="第二段")


def test_loop_executes_tool_then_returns_final_text():
    provider = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("call-1", "current_time", {"timezone": "UTC"})]),
        ProviderResponse(content="done"),
    )
    registry = ToolRegistry()
    registry.register(build_current_time_tool())
    events = list(AgentLoop(provider, registry, max_tool_rounds=2).run([Message(role="user", content="time?")]))
    assert [event.type for event in events] == ["tool_started", "tool_finished", "text_delta", "message_completed"]


def test_loop_forwards_provider_text_chunks_as_separate_deltas():
    events = list(AgentLoop(StreamingProvider(), ToolRegistry()).run([Message(role="user", content="go")]))
    deltas = [event.data["content"] for event in events if event.type == "text_delta"]
    assert deltas == ["第一段", "第二段"]
    assert events[-1].data["content"] == "第一段第二段"


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


def test_loop_requests_approval_before_executing_a_write_tool():
    calls = []
    registry = ToolRegistry()
    from iris_agent.tools.base import Tool
    registry.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: calls.append(True), requires_approval=True))
    events = list(AgentLoop(FakeProvider(ProviderResponse(tool_calls=[ToolCall("c", "write", {})])), registry, 1).run([]))
    assert [event.type for event in events] == ["tool_started", "tool_approval_requested"]
    assert events[-1].data["name"] == "write"
    assert calls == []


def test_loop_does_not_call_provider_when_already_cancelled():
    provider = FakeProvider(ProviderResponse(content="should not run"))

    events = list(AgentLoop(provider, ToolRegistry()).run([], is_cancelled=lambda: True))

    assert events == []
    assert len(provider.responses) == 1


def test_loop_discards_a_tool_result_that_returns_after_cancellation():
    cancelled = {"value": False}
    provider = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("c", "slow", {})]),
        ProviderResponse(content="must not continue"),
    )
    registry = ToolRegistry()
    from iris_agent.tools.base import Tool

    def cancel_during_tool():
        cancelled["value"] = True
        return "late result"

    registry.register(Tool("slow", "slow", {"type": "object", "properties": {}}, cancel_during_tool))

    events = list(
        AgentLoop(provider, registry).run([], is_cancelled=lambda: cancelled["value"])
    )

    assert [event.type for event in events] == ["tool_started"]
    assert len(provider.responses) == 1


def test_loop_runs_a_batch_of_fetch_page_calls_in_parallel_and_preserves_order():
    active = 0
    max_active = 0
    lock = threading.Lock()
    both_started = threading.Event()

    def fetch_page(url: str):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                both_started.set()
        both_started.wait(0.3)
        if url.endswith("slow"):
            time.sleep(0.03)
        with lock:
            active -= 1
        return url

    provider = FakeProvider(
        ProviderResponse(tool_calls=[
            ToolCall("fetch-1", "fetch_page", {"url": "https://example.com/slow"}),
            ToolCall("fetch-2", "fetch_page", {"url": "https://example.com/fast"}),
        ]),
        ProviderResponse(content="done"),
    )
    registry = ToolRegistry()
    registry.register(Tool("fetch_page", "fetch", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}, fetch_page))

    events = list(AgentLoop(provider, registry).run([]))

    assert max_active == 2
    assert [event.type for event in events[:4]] == ["tool_started", "tool_started", "tool_finished", "tool_finished"]
    assert [event.data["call_id"] for event in events if event.type == "tool_finished"] == ["fetch-1", "fetch-2"]


def test_loop_keeps_non_fetch_tools_serial():
    order = []

    def run(value: str):
        order.extend([f"start-{value}", f"end-{value}"])
        return value

    provider = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("a", "safe", {"value": "a"}), ToolCall("b", "safe", {"value": "b"})]),
        ProviderResponse(content="done"),
    )
    registry = ToolRegistry()
    registry.register(Tool("safe", "safe", {"type": "object", "properties": {"value": {"type": "string"}}}, run))

    list(AgentLoop(provider, registry).run([]))

    assert order == ["start-a", "end-a", "start-b", "end-b"]


def test_loop_drops_parallel_fetch_results_after_cancellation():
    cancelled = threading.Event()
    active = 0
    lock = threading.Lock()

    def fetch_page(url: str):
        nonlocal active
        with lock:
            active += 1
            if active == 2:
                cancelled.set()
        time.sleep(0.02)
        return url

    provider = FakeProvider(ProviderResponse(tool_calls=[
        ToolCall("fetch-1", "fetch_page", {"url": "https://example.com/1"}),
        ToolCall("fetch-2", "fetch_page", {"url": "https://example.com/2"}),
    ]))
    registry = ToolRegistry()
    registry.register(Tool("fetch_page", "fetch", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}, fetch_page))

    events = list(AgentLoop(provider, registry).run([], is_cancelled=cancelled.is_set))

    assert [event.type for event in events] == ["tool_started", "tool_started"]


def test_loop_snapshots_provider_for_all_rounds_of_one_request():
    first = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("c", "safe", {})]),
        ProviderResponse(content="old-provider"),
    )
    second = FakeProvider(ProviderResponse(content="new-provider"))
    loop = AgentLoop(first, ToolRegistry(), 1)
    loop.tools.register(Tool("safe", "safe", {"type": "object", "properties": {}}, lambda: loop.replace_provider(second)))

    old_events = list(loop.run([]))
    new_events = list(loop.run([]))

    assert old_events[-1].data["content"] == "old-provider"
    assert new_events[-1].data["content"] == "new-provider"


def test_replace_provider_is_safe_during_an_in_progress_stream_request():
    entered = threading.Event()
    release = threading.Event()

    class BlockingProvider:
        def stream(self, messages, tools):
            entered.set()
            release.wait(1)
            yield ProviderResponse(content="old")

    loop = AgentLoop(BlockingProvider(), ToolRegistry())
    output = []
    worker = threading.Thread(target=lambda: output.extend(loop.run([])))
    worker.start()
    assert entered.wait(1)
    loop.replace_provider(FakeProvider(ProviderResponse(content="new")))
    release.set()
    worker.join(1)

    assert output[-1].data["content"] == "old"
    assert list(loop.run([]))[-1].data["content"] == "new"


def test_get_provider_returns_current_provider_after_replacement():
    first = FakeProvider(ProviderResponse(content="first"))
    second = FakeProvider(ProviderResponse(content="second"))
    loop = AgentLoop(first, ToolRegistry())
    assert loop.get_provider() is first
    loop.replace_provider(second)
    assert loop.get_provider() is second


def test_switchable_provider_is_leased_for_entire_top_level_run():
    old = FakeProvider(
        ProviderResponse(tool_calls=[ToolCall("c", "switch", {})]),
        ProviderResponse(content="old-final"),
    )
    new = FakeProvider(ProviderResponse(content="new-final"))
    handle = SwitchableProvider(old)
    registry = ToolRegistry()
    registry.register(Tool("switch", "switch", {"type": "object", "properties": {}}, lambda: handle.replace(new)))
    loop = AgentLoop(handle, registry, 1)

    events = list(loop.run([]))

    assert events[-1].data["content"] == "old-final"
    assert list(loop.run([]))[-1].data["content"] == "new-final"
