"""Delegate task tool: run an isolated subagent and return its conclusion."""

from iris_agent.subagent.models import SubagentRequest, WorkflowStep
from iris_agent.subagent.roles import role_keys
from iris_agent.subagent.runner import SubagentRunner
from iris_agent.tools.base import Tool


ROLE_KEYS = list(role_keys())


def build_request_subagent_collaboration_tool() -> Tool:
    def request_subagent_collaboration(reason: str):
        return {"requested": True, "reason": reason}

    return Tool(
        "request_subagent_collaboration",
        "仅当任务确实复杂且包含多个可独立完成的步骤时调用，用于先询问用户是否启用子代理协作；未经用户确认不得调用委派工具。",
        {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "需要子代理协作的简短原因"},
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        request_subagent_collaboration,
        requires_approval=True,
        approval_context={"risk": "subagent_collaboration"},
    )


def build_delegate_task_tool(runner: SubagentRunner, session_id: str | None = None) -> Tool:
    def delegate(goal: str, context: str | None = None, allowed_tools: list[str] | None = None, max_rounds: int | None = None, background: bool = False, role: str | None = None):
        request = SubagentRequest(goal=goal, context=context, allowed_tools=allowed_tools, max_rounds=max_rounds, role=role)
        if background:
            submit = getattr(runner, "submit_background", None)
            if not callable(submit):
                raise ValueError("当前子代理运行器不支持后台执行")
            delegation_id = submit(request, session_id=session_id) if session_id else submit(request)
            return {"ok": True, "delegation_id": delegation_id, "status": "queued"}
        result = runner.run(request)
        payload = {"ok": result.ok, "result": result.result, "rounds": result.rounds}
        if result.delegation_id:
            payload.update({"delegation_id": result.delegation_id, "status": "succeeded" if result.ok else "failed"})
        return payload

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
                "role": {"type": "string", "enum": ROLE_KEYS, "description": "子代理角色模板"},
                "background": {"type": "boolean", "description": "后台执行并立即返回委派 ID"},
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
                    role=task.get("role"),
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
                            "role": {"type": "string", "enum": ROLE_KEYS, "description": "子代理角色模板"},
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


def build_delegate_workflow_tool(runner: SubagentRunner) -> Tool:
    def delegate_workflow(steps: list):
        parsed = [WorkflowStep(str(item.get("id", "")).strip(), str(item.get("goal", "")).strip(), list(item.get("depends_on", [])), item.get("context"), item.get("allowed_tools"), item.get("max_rounds"), item.get("role")) for item in steps if isinstance(item, dict)]
        if len(parsed) != len(steps):
            raise ValueError("工作流步骤必须是对象")
        result = runner.run_workflow(parsed)
        return {"steps": [{"id": step.id, "ok": result.steps[step.id].ok, "result": result.steps[step.id].result, "rounds": result.steps[step.id].rounds} for step in parsed]}
    return Tool("delegate_workflow", "按依赖关系执行子代理工作流；无依赖步骤并行，后续步骤自动得到前序结论。", {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "goal": {"type": "string"}, "depends_on": {"type": "array", "items": {"type": "string"}}, "context": {"type": "string"}, "allowed_tools": {"type": "array", "items": {"type": "string"}}, "max_rounds": {"type": "integer"}, "role": {"type": "string", "enum": ROLE_KEYS}}, "required": ["id", "goal"]}}}, "required": ["steps"]}, delegate_workflow, requires_approval=False)
