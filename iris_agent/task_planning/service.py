from __future__ import annotations

from dataclasses import asdict
import json
import time
from uuid import uuid4

from iris_agent.core.agent import AgentService
from iris_agent.core.models import AgentEvent, Message
from iris_agent.task_planning.models import TaskEvent, TaskPlan, TaskStep
from iris_agent.task_planning.repository import JsonTaskPlanRepository
from iris_agent.subagents.service import SubagentService


class TaskPlanService:
    def __init__(self, repository: JsonTaskPlanRepository, agent: AgentService, subagents: SubagentService | None = None) -> None:
        self.repository = repository
        self.agent = agent
        self.subagents = subagents
        self.repository.recover_interrupted()

    def create(self, session_id: str, goal: str, steps: list[dict[str, str]], skill_id: str | None = None) -> TaskPlan:
        goal = goal.strip()
        if not goal or not steps:
            raise ValueError("task goal and at least one step are required")
        task_steps = []
        for item in steps:
            title, instruction = item.get("title", "").strip(), item.get("instruction", "").strip()
            if not title or not instruction:
                raise ValueError("each task step needs a title and instruction")
            task_steps.append(TaskStep(f"step_{uuid4().hex}", title, instruction))
        now = time.time()
        plan = TaskPlan(f"plan_{uuid4().hex}", session_id, goal, task_steps, skill_id=skill_id, created_at=now, updated_at=now)
        self.repository.save(plan)
        return plan

    def create_from_goal(self, session_id: str, goal: str, skill_id: str | None = None, skill_instructions: str | None = None) -> TaskPlan:
        response = self.agent.loop.provider.complete([
            Message(role="system", content=(
                "You create concise, durable agent task plans. Return only valid JSON in this exact shape: "
                '{"steps":[{"title":"short title","instruction":"self-contained executable instruction"}]}. '
                "Create 1 to 8 ordered steps. Do not execute tools, claim results, or include markdown. "
                "Write instructions so one ReAct agent run can complete each step."
            )),
            Message(role="user", content=self._planning_request(goal, skill_instructions)),
        ], [])
        if response.tool_calls:
            raise ValueError("planner must return steps instead of tool calls")
        return self.create(session_id, goal, self._parse_steps(response.content), skill_id)

    def list(self, session_id: str | None = None) -> list[TaskPlan]:
        return self.repository.list(session_id)

    def get(self, plan_id: str) -> TaskPlan:
        return self.repository.get(plan_id)

    def delegate_step(self, plan_id: str, step_id: str, allowed_tools: list[str], max_tool_rounds: int | None = None) -> tuple[TaskPlan, list[AgentEvent]]:
        if self.subagents is None:
            raise ValueError("subagent delegation is unavailable")
        plan = self.repository.get(plan_id)
        step = next((item for item in plan.steps if item.id == step_id), None)
        if plan.status != "active" or step is None or step.status != "pending":
            raise ValueError("task step is not ready for delegation")
        child = self.subagents.create(plan.session_id, step.title, step.instruction, allowed_tools, max_tool_rounds, plan.id, step.id)
        step.status, step.subagent_id, step.error = "delegated", child.id, None
        plan.status = "waiting_subagent"
        self._record(step, "subagent_delegated", {"subagent_id": child.id, "allowed_tools": list(child.allowed_tools)})
        self._save(plan)
        child, events = self.subagents.run(child.id)
        return self._finish_delegated_step(plan, step, child.status, child.result, child.error, events)

    def run_next(self, plan_id: str, skill_instructions: str | None = None) -> tuple[TaskPlan, list[AgentEvent]]:
        plan = self.repository.get(plan_id)
        if plan.status != "active":
            raise ValueError("task plan is not ready to run")
        step = next((item for item in plan.steps if item.status == "pending"), None)
        if step is None:
            plan.status = "completed" if all(item.status == "completed" for item in plan.steps) else "failed"
            return self._save(plan), []
        step.status, step.error = "running", None
        self._record(step, "step_started", {"title": step.title})
        self._save(plan)
        prompt = f"You are executing one step of a durable task plan. Goal: {plan.goal}\nStep: {step.title}\nInstruction: {step.instruction}\nComplete only this step, then report the result."
        events = list(self.agent.run(plan.session_id, prompt, skill_instructions))
        return self._finish_step(plan, step, events)

    def resolve_approval(self, plan_id: str, approved: bool, skill_instructions: str | None = None) -> tuple[TaskPlan, list[AgentEvent]]:
        plan = self.repository.get(plan_id)
        step = next((item for item in plan.steps if item.status == "waiting_approval"), None)
        if plan.status != "waiting_approval" or step is None or not step.approval_call_id:
            raise ValueError("task plan is not waiting for approval")
        if step.subagent_id:
            if self.subagents is None:
                raise ValueError("subagent delegation is unavailable")
            child, events = self.subagents.resolve_approval(step.subagent_id, approved)
            return self._finish_delegated_step(plan, step, child.status, child.result, child.error, events)
        self._record(step, "approval_resolved", {"approved": approved, "call_id": step.approval_call_id})
        events = list(self.agent.resolve_tool_approval(plan.session_id, step.approval_call_id, approved, skill_instructions))
        return self._finish_step(plan, step, events)

    def _finish_step(self, plan: TaskPlan, step: TaskStep, events: list[AgentEvent]) -> tuple[TaskPlan, list[AgentEvent]]:
        for event in events:
            self._record_agent_event(step, event)
        approval = next((event for event in reversed(events) if event.type == "tool_approval_requested"), None)
        failure = next((event for event in reversed(events) if event.type == "error"), None)
        if approval:
            step.status = "waiting_approval"
            step.approval_call_id = str(approval.data["call_id"])
            plan.status = "waiting_approval"
            self._record(step, "approval_requested", {"call_id": step.approval_call_id})
        elif failure:
            step.status = "failed"
            step.error = str(failure.data.get("message", "step execution failed"))
            plan.status = "failed"
            self._record(step, "step_failed", {"message": step.error})
        else:
            step.status, step.approval_call_id = "completed", None
            plan.status = "completed" if all(item.status == "completed" for item in plan.steps) else "active"
            self._record(step, "step_completed")
        return self._save(plan), events

    def _finish_delegated_step(self, plan: TaskPlan, step: TaskStep, child_status: str, result: str, error: str | None, events: list[AgentEvent]) -> tuple[TaskPlan, list[AgentEvent]]:
        if child_status == "waiting_approval":
            step.status = "waiting_approval"
            child = self.subagents.get(step.subagent_id) if self.subagents and step.subagent_id else None
            step.approval_call_id = child.approval_call_id if child else None
            plan.status = "waiting_approval"
            self._record(step, "subagent_waiting_approval", {"subagent_id": step.subagent_id, "call_id": step.approval_call_id or ""})
        elif child_status == "completed":
            step.status, step.approval_call_id, step.result = "completed", None, result
            plan.status = "completed" if all(item.status == "completed" for item in plan.steps) else "active"
            self._record(step, "subagent_completed", {"subagent_id": step.subagent_id or "", "result_chars": len(result)})
        else:
            step.status, step.error = "failed", error or "subagent failed"
            plan.status = "failed"
            self._record(step, "subagent_failed", {"subagent_id": step.subagent_id or "", "message": step.error})
        return self._save(plan), events

    def _save(self, plan: TaskPlan) -> TaskPlan:
        plan.updated_at = time.time()
        return self.repository.save(plan)

    @staticmethod
    def data(plan: TaskPlan) -> dict:
        return asdict(plan)

    @staticmethod
    def _record(step: TaskStep, event_type: str, details: dict[str, object] | None = None) -> None:
        step.events.append(TaskEvent(time.time(), event_type, details or {}))
        del step.events[:-100]

    def _record_agent_event(self, step: TaskStep, event: AgentEvent) -> None:
        details: dict[str, object] = {}
        if event.type == "react_step":
            details["phase"] = str(event.data.get("phase", ""))
            if event.data.get("name"):
                details["tool"] = str(event.data["name"])
        elif event.type in {"tool_started", "tool_finished", "tool_approval_requested"}:
            details["tool"] = str(event.data.get("name", ""))
            if "ok" in event.data:
                details["ok"] = bool(event.data["ok"])
            if event.data.get("error_message"):
                details["message"] = str(event.data["error_message"])[:500]
        elif event.type == "text_delta":
            details["content"] = str(event.data.get("content", ""))[:1_000]
        elif event.type == "error":
            details["code"] = str(event.data.get("code", ""))
            details["message"] = str(event.data.get("message", ""))[:500]
        self._record(step, event.type, details)

    @staticmethod
    def _planning_request(goal: str, skill_instructions: str | None) -> str:
        request = f"Goal: {goal.strip()}"
        if skill_instructions:
            request += f"\nActive Skill context:\n{skill_instructions}"
        return request

    @staticmethod
    def _parse_steps(content: str) -> list[dict[str, str]]:
        payload = content.strip()
        if payload.startswith("```") and payload.endswith("```"):
            payload = "\n".join(payload.splitlines()[1:-1]).strip()
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("planner returned invalid JSON") from exc
        steps = value.get("steps") if isinstance(value, dict) else None
        if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
            raise ValueError("planner must return between 1 and 8 steps")
        normalized: list[dict[str, str]] = []
        for item in steps:
            if not isinstance(item, dict):
                raise ValueError("planner returned an invalid step")
            title, instruction = item.get("title"), item.get("instruction")
            if not isinstance(title, str) or not isinstance(instruction, str):
                raise ValueError("planner returned an invalid step")
            normalized.append({"title": title, "instruction": instruction})
        return normalized
