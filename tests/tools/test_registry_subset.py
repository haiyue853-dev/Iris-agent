from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def _tool(name: str) -> Tool:
    return Tool(name, "desc", {"type": "object", "properties": {}}, lambda: None)


def test_subset_returns_only_selected():
    registry = ToolRegistry()
    registry.register(_tool("a"))
    registry.register(_tool("b"))
    registry.register(_tool("c"))

    sub = registry.subset(["a", "c"])

    names = {schema["function"]["name"] for schema in sub.schemas()}
    assert names == {"a", "c"}


def test_subset_skips_unknown_names():
    registry = ToolRegistry()
    registry.register(_tool("a"))

    sub = registry.subset(["a", "unknown"])

    names = [schema["function"]["name"] for schema in sub.schemas()]
    assert names == ["a"]


def test_subset_is_empty_for_no_matches():
    registry = ToolRegistry()
    registry.register(_tool("a"))

    sub = registry.subset(["unknown"])

    assert sub.schemas() == []


def test_subset_does_not_mutate_original():
    registry = ToolRegistry()
    registry.register(_tool("a"))
    registry.register(_tool("b"))

    registry.subset(["a"])

    names = {schema["function"]["name"] for schema in registry.schemas()}
    assert names == {"a", "b"}
