from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


StepStatus = Literal["pending", "running", "delegated", "waiting_approval", "completed", "failed"]
PlanStatus = Literal["active", "waiting_subagent", "waiting_approval", "completed", "failed"]


@dataclass(slots=True)
class TaskEvent:
    at: float
    type: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class TaskStep:
    id: str
    title: str
    instruction: str
    status: StepStatus = "pending"
    approval_call_id: str | None = None
    subagent_id: str | None = None
    result: str = ""
    error: str | None = None
    events: list[TaskEvent] = field(default_factory=list)


@dataclass(slots=True)
class TaskPlan:
    id: str
    session_id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    skill_id: str | None = None
    status: PlanStatus = "active"
    created_at: float = 0
    updated_at: float = 0
