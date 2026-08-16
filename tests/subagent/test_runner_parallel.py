import threading
import time

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message, ProviderResponse
from iris_agent.subagent.models import SubagentRequest
from iris_agent.subagent.runner import SubagentRunner
from iris_agent.tools.registry import ToolRegistry


class ConcurrencyProvider:
    """Thread-safe fake that reports the observed peak concurrency and echoes the goal."""

    def __init__(self, delay: float = 0.05, fail_on: str | None = None):
        self.delay = delay
        self.fail_on = fail_on
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def complete(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        goal = next((m.content for m in messages if m.role == "user"), "")
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._active -= 1
        if self.fail_on is not None and self.fail_on in goal:
            raise ProviderError("模型服务调用失败")
        return ProviderResponse(content=f"结论:{goal}", tool_calls=[])


def _runner(provider, **kwargs) -> SubagentRunner:
    defaults = dict(
        provider=provider,
        tool_subset=ToolRegistry().subset,
        system_prompt="你是子代理",
        default_allowed_tools=["read_file"],
    )
    defaults.update(kwargs)
    return SubagentRunner(**defaults)


def test_run_parallel_returns_results_in_input_order():
    provider = ConcurrencyProvider(delay=0.02)
    runner = _runner(provider, max_parallel_tasks=3)

    results = runner.run_parallel([SubagentRequest("任务一"), SubagentRequest("任务二"), SubagentRequest("任务三")])

    assert [r.result for r in results] == ["结论:任务一", "结论:任务二", "结论:任务三"]
    assert all(r.ok for r in results)


def test_run_parallel_runs_concurrently():
    provider = ConcurrencyProvider(delay=0.08)
    runner = _runner(provider, max_parallel_tasks=3)

    runner.run_parallel([SubagentRequest("a"), SubagentRequest("b"), SubagentRequest("c")])

    # 串行执行需要约 0.24s；若真并行，峰值并发应 >= 2。
    assert provider.max_active >= 2


def test_run_parallel_respects_max_workers():
    provider = ConcurrencyProvider(delay=0.03)
    runner = _runner(provider, max_parallel_tasks=5)

    runner.run_parallel([SubagentRequest("a"), SubagentRequest("b"), SubagentRequest("c")], max_workers=1)

    assert provider.max_active == 1


def test_run_parallel_empty_returns_empty():
    runner = _runner(ConcurrencyProvider())
    assert runner.run_parallel([]) == []


def test_run_parallel_isolates_single_failure():
    provider = ConcurrencyProvider(delay=0.02, fail_on="会失败")
    runner = _runner(provider, max_parallel_tasks=3)

    results = runner.run_parallel([SubagentRequest("正常任务"), SubagentRequest("会失败的任务"), SubagentRequest("另一个正常任务")])

    assert results[0].ok is True
    assert results[1].ok is False
    assert "异常" in results[1].result
    assert results[2].ok is True


def test_run_parallel_clamps_workers_to_request_count():
    provider = ConcurrencyProvider(delay=0.02)
    runner = _runner(provider, max_parallel_tasks=10)

    runner.run_parallel([SubagentRequest("a"), SubagentRequest("b")])

    assert provider.max_active <= 2
