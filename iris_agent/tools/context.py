"""Cooperative deadline and progress for built-in tool handlers."""
from contextvars import ContextVar
from time import monotonic

from iris_agent.tools.base import ToolInvocationError


execution_context = ContextVar("tool_execution_context", default=None)


def remaining(deadline: float) -> float:
    context = execution_context.get()
    if context is not None:
        deadline = min(deadline, context[0])
        if context[1].is_set():
            raise ToolInvocationError("tool_cancelled", "工具调用已取消")
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise ToolInvocationError("tool_timeout", "工具执行超时")
    return seconds


def report_progress(**data):
    context = execution_context.get()
    if context is not None and not context[1].is_set():
        context[2](data)
