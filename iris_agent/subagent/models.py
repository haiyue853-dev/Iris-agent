"""Subagent delegation models (P4)."""

from dataclasses import dataclass


@dataclass(slots=True)
class SubagentRequest:
    goal: str
    context: str | None = None
    allowed_tools: list[str] | None = None
    max_rounds: int | None = None
    role: str | None = None


@dataclass(slots=True)
class SubagentResult:
    ok: bool
    result: str
    rounds: int
    delegation_id: str | None = None


@dataclass(slots=True)
class WorkflowStep:
    id: str
    goal: str
    depends_on: list[str]
    context: str | None = None
    allowed_tools: list[str] | None = None
    max_rounds: int | None = None
    role: str | None = None


@dataclass(slots=True)
class WorkflowResult:
    steps: dict[str, SubagentResult]
