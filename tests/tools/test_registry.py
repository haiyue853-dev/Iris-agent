import pytest

from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def echo(value: str):
    return {"value": value}


def test_registry_validates_required_parameters():
    registry = ToolRegistry()
    registry.register(Tool("echo", "echo", {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}, echo))
    result = registry.invoke("echo", {})
    assert result.ok is False
    assert result.error_code == "invalid_tool_arguments"


def test_registry_rejects_duplicate_names():
    registry = ToolRegistry()
    tool = Tool("echo", "echo", {"type": "object", "properties": {}}, echo)
    registry.register(tool)
    with pytest.raises(ValueError):
        registry.register(tool)
