from __future__ import annotations

from dataclasses import asdict
import time
from uuid import uuid4

from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import AgentEvent
from iris_agent.subagents.models import SubagentEvent, SubagentTask
from iris_agent.subagents.repository import JsonSubagentRepository


class SubagentService:
    def __init__(self, repository: JsonSubagentRepository, agent: AgentService, max_concurrent: int = 2, max_tool_rounds: int = 4) -> None:
        self.repository = repository
        self.agent = agent
        self.max_concurrent = max_concurrent
        self.max_tool_rounds = max_tool_rounds
        self.repository.recover_interrupted()

    def create(self, parent_session_id: str, title: str, instruction: str, allowed_tools: list[str], max_tool_rounds: int | None = None, parent_plan_id: str | None = None, parent_step_id: str | None = None) -> SubagentTask:
        title, instruction = title.strip(), instruction.strip()
        if not title or not instruction:
            raise ValueError("subagent title and instruction are required")
        rounds = max_tool_rounds or self.max_tool_rounds
        if not 1 <= rounds <= self.max_tool_rounds:
            raise ValueError("subagent tool round limit is invalid")
        child_tools = self.agent.loop.tools.filtered(allowed_tools)
        child_session = self.agent.sessions.create(f"Subagent: {title}")
        now = time.time()
        task = SubagentTask(f"subagent_{uuid4().hex}", parent_session_id, child_session.id, parent_plan_id, parent_step_id, title, instruction, tuple(tool.name for tool in child_tools.tools_with_prefix("")), rounds, created_at=now, updated_at=now)
        self._record(task, "created", {"allowed_tools": list(task.allowed_tools)})
        return self._save(task)

    def list(self, parent_session_id: str | None = None) -> list[SubagentTask]:
        return self.repository.list(parent_session_id)

    def get(self, task_id: str) -> SubagentTask:
        return self.repository.get(task_id)

    def run(self, task_id: str) -> tuple[SubagentTask, list[AgentEvent]]:
        task = self.repository.get(task_id)
        if task.status != "queued":
            raise ValueError("subagent is not ready to run")
        active = sum(item.status in {"running", "waiting_approval"} for item in self.repository.list())
        if active >= self.max_concurrent:
            raise ValueError("subagent concurrency limit reached")
        task.status, task.error = "running", None
        self._record(task, "started")
        self._save(task)
        events = list(self._agent_for(task).run(task.session_id, task.instruction))
        return self._finish(task, events)

    def resolve_approval(self, task_id: str, approved: bool) -> tuple[SubagentTask, list[AgentEvent]]:
        task = self.repository.get(task_id)
        if task.status != "waiting_approval" or not task.approval_call_id:
            raise ValueError("subagent is not waiting for approval")
        self._record(task, "approval_resolved", {"approved": approved, "call_id": task.approval_call_id})
        events = list(self._agent_for(task).resolve_tool_approval(task.session_id, task.approval_call_id, approved))
        return self._finish(task, events)

    def _agent_for(self, task: SubagentTask) -> AgentService:
        tools = self.agent.loop.tools.filtered(task.allowed_tools)
        loop = AgentLoop(self.agent.loop.provider, tools, task.max_tool_rounds)
        prompt = f"You are an isolated subagent. Complete only your assigned task and return a concise factual result. Do not delegate further.\n\n{self.agent.system_prompt}"
        return AgentService(loop, self.agent.sessions, prompt, self.agent.context, self.agent.memory)

    def _finish(self, task: SubagentTask, events: list[AgentEvent]) -> tuple[SubagentTask, list[AgentEvent]]:
        for event in events:
            self._record_agent_event(task, event)
        approval = next((event for event in reversed(events) if event.type == "tool_approval_requested"), None)
        failure = next((event for event in reversed(events) if event.type == "error"), None)
        if approval:
            task.status = "waiting_approval"
            task.approval_call_id = str(approval.data["call_id"])
            self._record(task, "approval_requested", {"call_id": task.approval_call_id})
        elif failure:
            task.status, task.error = "failed", str(failure.data.get("message", "subagent failed"))
            self._record(task, "failed", {"message": task.error})
        else:
            task.status, task.approval_call_id = "completed", None
            task.result = "".join(str(event.data.get("content", "")) for event in events if event.type == "text_delta")[:4_000]
            self._record(task, "completed", {"result_chars": len(task.result)})
        return self._save(task), events

    def _save(self, task: SubagentTask) -> SubagentTask:
        task.updated_at = time.time()
        return self.repository.save(task)

    @staticmethod
    def data(task: SubagentTask) -> dict:
        return asdict(task)

    @staticmethod
    def _record(task: SubagentTask, event_type: str, details: dict[str, object] | None = None) -> None:
        task.events.append(SubagentEvent(time.time(), event_type, details or {}))
        del task.events[:-100]

    def _record_agent_event(self, task: SubagentTask, event: AgentEvent) -> None:
        details: dict[str, object] = {}
        if event.type in {"tool_started", "tool_finished", "tool_approval_requested"}:
            details["tool"] = str(event.data.get("name", ""))
            details["ok"] = bool(event.data.get("ok", True))
        elif event.type == "text_delta":
            details["content"] = str(event.data.get("content", ""))[:1_000]
        elif event.type == "error":
            details["message"] = str(event.data.get("message", ""))[:500]
        self._record(task, event.type, details)
