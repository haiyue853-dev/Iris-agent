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


def build_delegate_tasks_tool(runner: SubagentRunner) -> Tool:
    def delegate_many(tasks: list, max_workers: int | None = None):
        requests: list[SubagentRequest] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            goal = str(task.get("goal", "")).strip()
            if not goal:
                continue
            requests.append(
                SubagentRequest(
                    goal=goal,
                    context=task.get("context"),
                    allowed_tools=task.get("allowed_tools"),
                    max_rounds=task.get("max_rounds"),
                )
            )
        results = runner.run_parallel(requests, max_workers=max_workers)
        succeeded = sum(1 for result in results if result.ok)
        return {
            "results": [{"ok": result.ok, "result": result.result, "rounds": result.rounds} for result in results],
            "total": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
        }

    return Tool(
        "delegate_tasks",
        "把多个独立子任务一次性并行委派给多个隔离子代理执行，返回各任务结论的汇总（适合同时查多路资料再综合）",
        {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "要并行执行的子任务列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "description": "子任务目标（必填）"},
                            "context": {"type": "string", "description": "可选背景片段"},
                            "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "可选工具白名单"},
                            "max_rounds": {"type": "integer", "description": "可选迭代预算"},
                        },
                        "required": ["goal"],
                    },
                },
                "max_workers": {"type": "integer", "description": "可选最大并行数，默认由配置决定"},
            },
            "required": ["tasks"],
        },
        delegate_many,
        requires_approval=False,
    )
