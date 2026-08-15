"""Subagent delegation models (P4)."""

from dataclasses import dataclass


@dataclass(slots=True)
class SubagentRequest:
    goal: str
    context: str | None = None
    allowed_tools: list[str] | None = None
    max_rounds: int | None = None


@dataclass(slots=True)
class SubagentResult:
    ok: bool
    result: str
    rounds: int
