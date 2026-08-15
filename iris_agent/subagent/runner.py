"""Subagent runner: execute an isolated delegated task via AgentLoop."""

from collections.abc import Callable

from iris_agent.core.agent import AgentLoop
from iris_agent.core.models import Message
from iris_agent.providers.base import ModelProvider
from iris_agent.subagent.models import SubagentRequest, SubagentResult
from iris_agent.tools.registry import ToolRegistry


class SubagentRunner:
    def __init__(
        self,
        provider: ModelProvider,
        tool_subset: Callable[[list[str]], ToolRegistry],
        system_prompt: str,
        max_goal_chars: int = 2000,
        max_context_chars: int = 4000,
        max_result_chars: int = 4000,
        default_max_rounds: int = 6,
        default_allowed_tools: list[str] | None = None,
    ):
        self.provider = provider
        self.tool_subset = tool_subset
        self.system_prompt = system_prompt
        self.max_goal_chars = max_goal_chars
        self.max_context_chars = max_context_chars
        self.max_result_chars = max_result_chars
        self.default_max_rounds = default_max_rounds
        self.default_allowed_tools = default_allowed_tools or []

    def run(self, request: SubagentRequest) -> SubagentResult:
        goal = request.goal[: self.max_goal_chars]
        messages = [Message(role="system", content=self.system_prompt)]
        if request.context:
            context = request.context[: self.max_context_chars]
            messages.append(Message(role="system", content=f"[上下文] {context}"))
        messages.append(Message(role="user", content=goal))

        allowed = request.allowed_tools if request.allowed_tools is not None else self.default_allowed_tools
        tools = self.tool_subset(allowed)
        max_rounds = request.max_rounds if request.max_rounds is not None else self.default_max_rounds
        loop = AgentLoop(self.provider, tools, max_rounds)

        result = ""
        ok = False
        rounds = 0
        for event in loop.run(messages):
            if event.type == "message_completed":
                result = str(event.data.get("content", ""))
                ok = True
            elif event.type == "tool_finished":
                rounds += 1
        return SubagentResult(ok=ok, result=result[: self.max_result_chars], rounds=rounds)
