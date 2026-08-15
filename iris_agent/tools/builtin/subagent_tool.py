"""Delegate task tool: run an isolated subagent and return its conclusion."""

from iris_agent.subagent.models import SubagentRequest
from iris_agent.subagent.runner import SubagentRunner
from iris_agent.tools.base import Tool


def build_delegate_task_tool(runner: SubagentRunner) -> Tool:
    def delegate(goal: str, context: str | None = None, allowed_tools: list[str] | None = None, max_rounds: int | None = None):
        result = runner.run(SubagentRequest(goal=goal, context=context, allowed_tools=allowed_tools, max_rounds=max_rounds))
        return {"ok": result.ok, "result": result.result, "rounds": result.rounds}

    return Tool(
        "delegate_task",
        "把一个独立子任务委派给隔离的子代理执行，只返回文本结论",
        {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "子任务目标（必填）"},
                "context": {"type": "string", "description": "可选背景片段"},
                "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "可选工具白名单"},
                "max_rounds": {"type": "integer", "description": "可选迭代预算"},
            },
            "required": ["goal"],
        },
        delegate,
        requires_approval=False,
    )
