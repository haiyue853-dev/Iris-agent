import hashlib
import json
import math
import re
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

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

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schema_hash(self) -> str:
        payload = json.dumps(self.schemas(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def replace_prefix(self, prefix: str, tools: list[Tool]) -> None:
        for name in tuple(self._tools):
            if name.startswith(prefix):
                del self._tools[name]
        for tool in tools:
            self.register(tool)

    def tools_with_prefix(self, prefix: str) -> list[Tool]:
        return [tool for name, tool in self._tools.items() if name.startswith(prefix)]

    def subset(self, names: list[str]) -> "ToolRegistry":
        """Return a new registry containing only the named tools (unknown names skipped)."""
        sub = ToolRegistry()
        for name in names:
            tool = self._tools.get(name)
            if tool is not None:
                sub.register(tool)
        return sub

    def copy(self) -> "ToolRegistry":
        sub = ToolRegistry()
        for tool in self._tools.values():
            sub.register(tool)
        return sub

    def requires_approval(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool is not None and tool.requires_approval

    def execution_timeout(self, name: str, default: float) -> float:
        tool = self._tools.get(name)
        return min(default, tool.timeout_seconds) if tool and tool.timeout_seconds else default

    def approval_context(self, name: str) -> dict[str, Any] | None:
        tool = self._tools.get(name)
        return None if tool is None else tool.approval_context

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecutionResult(False, error_code="unknown_tool", error_message=f"未知工具: {name}")
        normalized = _normalize_value(arguments, tool.parameters)
        error = _validate(tool.parameters, normalized)
        if error:
            return ToolExecutionResult(False, error_code="invalid_tool_arguments", error_message=error)
        return tool.invoke(normalized)


def _normalize_value(value: Any, schema: dict[str, Any]) -> Any:
    raw_types = schema.get("type")
    accepted_types = {raw_types} if isinstance(raw_types, str) else set(raw_types or ())
    normalized = value

    if isinstance(value, str) and "string" not in accepted_types:
        stripped = value.strip()
        if "boolean" in accepted_types and stripped.casefold() in {"true", "false"}:
            normalized = stripped.casefold() == "true"
        elif "integer" in accepted_types and re.fullmatch(r"-?(?:0|[1-9]\d*)", stripped):
            normalized = int(stripped)
        elif "number" in accepted_types:
            try:
                number = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                number = None
            if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number):
                normalized = number
        elif accepted_types.intersection({"array", "object"}):
            try:
                container = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                container = None
            if "array" in accepted_types and isinstance(container, list):
                normalized = container
            elif "object" in accepted_types and isinstance(container, dict):
                normalized = container

    if isinstance(normalized, dict):
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", {})
        changed = False
        result: dict[str, Any] = {}
        for name, item in normalized.items():
            item_schema = properties.get(name, additional if isinstance(additional, dict) else {})
            converted = _normalize_value(item, item_schema)
            result[name] = converted
            changed = changed or converted is not item
        return result if changed else normalized
    if isinstance(normalized, list) and isinstance(schema.get("items"), dict):
        result = [_normalize_value(item, schema["items"]) for item in normalized]
        return result if any(converted is not item for converted, item in zip(result, normalized)) else normalized
    return normalized


def _validate(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    if not isinstance(arguments, dict):
        return "工具参数必须是对象"
    try:
        validator_class = validator_for(schema, default=Draft202012Validator)
        validator_class.check_schema(schema)
        error = next(validator_class(schema).iter_errors(arguments), None)
    except SchemaError:
        return "工具参数结构无效"
    if error is None:
        return None

    path = ""
    for part in error.absolute_path:
        path += f"[{part}]" if isinstance(part, int) else f"{'.' if path else ''}{part}"
    location = f"参数 {path}" if path else "工具参数"
    if error.validator == "required" and isinstance(error.instance, dict):
        missing = next((name for name in error.validator_value if name not in error.instance), None)
        if missing is not None:
            return f"缺少必填参数: {missing}"
    if error.validator == "additionalProperties":
        properties = error.schema.get("properties", {})
        patterns = error.schema.get("patternProperties", {})
        extras = [
            str(name)
            for name in error.instance
            if name not in properties and not any(re.search(pattern, str(name)) for pattern in patterns)
        ]
        suffix = f": {', '.join(extras)}" if extras else ""
        return f"{location} 包含不支持的字段{suffix}"
    if error.validator == "type":
        return f"{location} 类型应为 {error.validator_value}"
    if error.validator == "enum":
        return f"{location} 不在允许的取值范围内"
    return f"{location} 不符合 JSON Schema 约束"
