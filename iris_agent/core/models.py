from dataclasses import dataclass, field
from typing import Any, Literal
import uuid

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    argument_error: str | None = None


@dataclass(slots=True)
class ToolResult:
    call_id: str
    name: str
    value: Any = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    attachment_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"message_{uuid.uuid4().hex}")

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported message role: {self.role}")
        if not isinstance(self.attachment_ids, list) or any(not isinstance(item, str) or not item for item in self.attachment_ids):
            raise ValueError("attachment_ids must be a list of non-empty strings")


@dataclass(slots=True)
class ProviderResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(slots=True)
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}
