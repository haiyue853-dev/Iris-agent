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


def test_registry_enforces_composed_json_schema_constraints():
    registry = ToolRegistry()
    registry.register(Tool(
        "lookup",
        "lookup",
        {
            "type": "object",
            "properties": {
                "target": {
                    "oneOf": [
                        {"type": "string", "pattern": "^https://"},
                        {
                            "type": "object",
                            "properties": {"id": {"type": "integer", "minimum": 1}},
                            "required": ["id"],
                            "additionalProperties": False,
                        },
                    ],
                },
            },
            "required": ["target"],
            "additionalProperties": False,
        },
        lambda target: {"target": target},
    ))

    assert registry.invoke("lookup", {"target": "https://example.test"}).ok is True
    assert registry.invoke("lookup", {"target": {"id": 1}}).ok is True
    assert registry.invoke("lookup", {"target": "http://example.test"}).error_code == "invalid_tool_arguments"
    assert registry.invoke("lookup", {"target": {"id": 0}}).error_code == "invalid_tool_arguments"
    assert registry.invoke("lookup", {"target": 3}).error_code == "invalid_tool_arguments"


def test_registry_coerces_stringified_values_using_the_tool_schema():
    registry = ToolRegistry()
    registry.register(Tool(
        "search",
        "search",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "exact": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "filters": {
                    "type": "object",
                    "properties": {"score": {"type": "number"}},
                    "required": ["score"],
                },
                "literal": {"type": "string"},
            },
            "required": ["limit", "exact", "tags", "filters", "literal"],
        },
        lambda **arguments: arguments,
    ))

    result = registry.invoke("search", {
        "limit": "10",
        "exact": "false",
        "tags": '["python", "mcp"]',
        "filters": '{"score": "0.75"}',
        "literal": '{"must": "stay a string"}',
    })

    assert result.ok is True
    assert result.value == {
        "limit": 10,
        "exact": False,
        "tags": ["python", "mcp"],
        "filters": {"score": 0.75},
        "literal": '{"must": "stay a string"}',
    }
