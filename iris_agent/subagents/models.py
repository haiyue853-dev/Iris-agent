from dataclasses import dataclass, field
from typing import Literal


SubagentStatus = Literal["queued", "running", "waiting_approval", "completed", "failed"]


@dataclass(slots=True)
class SubagentEvent:
    at: float
    type: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class SubagentTask:
    id: str
    parent_session_id: str
    session_id: str
    parent_plan_id: str | None
    parent_step_id: str | None
    title: str
    instruction: str
    allowed_tools: tuple[str, ...]
    max_tool_rounds: int
    status: SubagentStatus = "queued"
    approval_call_id: str | None = None
    result: str = ""
    error: str | None = None
    events: list[SubagentEvent] = field(default_factory=list)
    created_at: float = 0
    updated_at: float = 0
