from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class ToolExecutionResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def invoke(self, arguments: dict[str, Any]) -> ToolExecutionResult:
        try:
            return ToolExecutionResult(ok=True, value=self.handler(**arguments))
        except ToolInvocationError as exc:
            return ToolExecutionResult(ok=False, error_code=exc.code, error_message=str(exc))
        except Exception as exc:
            return ToolExecutionResult(ok=False, error_code="tool_execution_error", error_message=str(exc))

    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolInvocationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
