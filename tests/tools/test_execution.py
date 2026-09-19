import threading

from iris_agent.core.agent import AgentLoop
from iris_agent.core.models import ToolCall
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def test_per_tool_timeout_bounds_a_blocking_handler():
    from iris_agent.tools.execution import ToolExecutor
    release = threading.Event()
    registry = ToolRegistry()
    registry.register(Tool('slow', '', {'type': 'object'}, lambda: release.wait(2), timeout_seconds=.04))
    try:
        events = list(ToolExecutor(timeout_seconds=1).execute(ToolCall('c', 'slow'), registry, lambda: False))
        assert events[-1].data['error_code'] == 'tool_timeout'
        assert events[-1].data['duration_ms'] < 500
    finally:
        release.set()


def test_cancel_returns_without_waiting_for_blocked_tool():
    started, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    registry = ToolRegistry()
    registry.register(Tool('slow', '', {'type': 'object'}, lambda: started.set() or release.wait(2)))
    events = []
    loop = AgentLoop(None, registry)
    worker = threading.Thread(target=lambda: events.extend(loop.execute_tool_call(ToolCall('c', 'slow'), registry, cancelled.is_set)))
    worker.start()
    try:
        assert started.wait(1)
        cancelled.set()
        worker.join(.3)
        assert not worker.is_alive()
        assert not events
    finally:
        release.set()
        worker.join(1)


def test_timeout_reports_failure_and_drops_late_success():
    from iris_agent.tools.execution import ToolExecutor

    release = threading.Event()
    registry = ToolRegistry()
    registry.register(Tool('slow', '', {'type': 'object'}, lambda: release.wait(1)))
    loop = AgentLoop(None, registry, executor=ToolExecutor(timeout_seconds=.04, max_workers=1))
    try:
        events = list(loop.execute_tool_call(ToolCall('c', 'slow'), registry, lambda: False))
        assert events[-1].data['error_code'] == 'tool_timeout'
        assert events[-1].data['ok'] is False
    finally:
        release.set()


def test_silent_stream_is_cancelled_and_exceptions_become_tool_failures():
    class Execution:
        def __init__(self):
            self.started = threading.Event()
            self.stopped = threading.Event()

        def cancel(self):
            self.stopped.set()

        def stream(self):
            self.started.set()
            self.stopped.wait(1)
            raise ValueError('stream broke')
            yield

    execution = Execution()
    registry = ToolRegistry()
    registry.register(Tool('command', '', {'type': 'object'}, lambda: execution))
    cancelled = threading.Event()
    events = []
    worker = threading.Thread(target=lambda: events.extend(AgentLoop(None, registry).execute_tool_call(ToolCall('c', 'command'), registry, cancelled.is_set)))
    worker.start()
    try:
        assert execution.started.wait(1)
        cancelled.set()
        worker.join(.3)
        assert execution.stopped.is_set()
        assert not worker.is_alive()
    finally:
        execution.cancel()
        worker.join(1)


def test_timed_out_workers_keep_their_slot_until_they_really_exit():
    from iris_agent.tools.execution import ToolExecutor
    release = threading.Event()
    calls = []
    registry = ToolRegistry()
    registry.register(Tool('slow', '', {'type': 'object'}, lambda: calls.append(1) or release.wait(1)))
    loop = AgentLoop(None, registry, executor=ToolExecutor(timeout_seconds=.04, max_workers=1))
    try:
        assert list(loop.execute_tool_call(ToolCall('a', 'slow'), registry, lambda: False))[-1].data['error_code'] == 'tool_timeout'
        assert list(loop.execute_tool_call(ToolCall('b', 'slow'), registry, lambda: False))[-1].data['error_code'] == 'tool_executor_busy'
        assert calls == [1]
    finally:
        release.set()


def test_stream_exception_is_a_finished_failure():
    class Broken:
        def stream(self):
            yield {'output': 'partial'}
            raise ValueError('broken stream')
    registry = ToolRegistry()
    registry.register(Tool('broken', '', {'type': 'object'}, Broken))
    events = list(AgentLoop(None, registry).execute_tool_call(ToolCall('c', 'broken'), registry, lambda: False))
    assert events[0].type == 'tool_progress'
    assert events[-1].data['error_code'] == 'tool_execution_error'


def test_timeout_skips_remaining_operations_in_same_batch():
    from iris_agent.core.models import ProviderResponse
    from iris_agent.tools.execution import ToolExecutor
    release = threading.Event()
    writes = []

    class Provider:
        calls = 0
        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall('a', 'slow'), ToolCall('b', 'write')])
            assert tools == []
            assert messages[-2].tool_call_id == 'b'
            return ProviderResponse(content='stopped')

    registry = ToolRegistry()
    registry.register(Tool('slow', '', {'type': 'object'}, lambda: release.wait(1)))
    registry.register(Tool('write', '', {'type': 'object'}, lambda: writes.append(1)))
    try:
        events = list(AgentLoop(Provider(), registry, executor=ToolExecutor(.04)).run([]))
        assert events[-1].data['content'] == 'stopped'
        assert writes == []
    finally:
        release.set()
