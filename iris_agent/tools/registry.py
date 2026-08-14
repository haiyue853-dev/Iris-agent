from typing import Any

from .base import Tool, ToolExecutionResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def replace_prefix(self, prefix: str, tools: list[Tool]) -> None:
        for name in tuple(self._tools):
            if name.startswith(prefix):
                del self._tools[name]
        for tool in tools:
            self.register(tool)

    def tools_with_prefix(self, prefix: str) -> list[Tool]:
        return [tool for name, tool in self._tools.items() if name.startswith(prefix)]

    def filtered(self, names: list[str] | tuple[str, ...]) -> "ToolRegistry":
        selected = ToolRegistry()
        unknown = [name for name in names if name not in self._tools]
        if unknown:
            raise ValueError(f"unknown tools: {', '.join(unknown)}")
        for name in names:
            selected.register(self._tools[name])
        return selected

    def requires_approval(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool is not None and tool.requires_approval

    def approval_context(self, name: str) -> dict[str, Any] | None:
        tool = self._tools.get(name)
        return None if tool is None else tool.approval_context

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecutionResult(False, error_code="unknown_tool", error_message=f"未知工具: {name}")
        error = _validate(tool.parameters, arguments)
        if error:
            return ToolExecutionResult(False, error_code="invalid_tool_arguments", error_message=error)
        return tool.invoke(arguments)


def _validate(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    if not isinstance(arguments, dict):
        return "工具参数必须是对象"
    for name in schema.get("required", []):
        if name not in arguments:
            return f"缺少必填参数: {name}"
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
    for name, value in arguments.items():
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and name not in properties:
            return f"不支持的参数: {name}"
        expected = properties.get(name, {}).get("type")
        is_numeric_boolean = expected in {"integer", "number"} and isinstance(value, bool)
        if expected in types and (is_numeric_boolean or not isinstance(value, types[expected])):
            return f"参数 {name} 类型应为 {expected}"
    return None
