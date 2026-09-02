from iris_agent.tools.base import Tool
from iris_agent.tools.capabilities import CapabilityResolver
from iris_agent.tools.registry import ToolRegistry


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in ("recall", "read_file", "write_file", "web_search"):
        registry.register(Tool(name, name, {"type": "object", "properties": {}}, lambda: None))
    return registry


def test_resolver_returns_only_requested_toolsets_in_stable_order():
    resolver = CapabilityResolver(
        _registry(),
        {"safe": ("recall", "read_file"), "research": ("web_search",)},
    )

    first = resolver.resolve(("research", "safe"))
    second = resolver.resolve(("research", "safe"))

    assert first.names() == ("web_search", "recall", "read_file")
    assert first.schema_hash() == second.schema_hash()


def test_resolver_rejects_unknown_toolset():
    resolver = CapabilityResolver(_registry(), {"safe": ("recall",)})

    try:
        resolver.resolve(("missing",))
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown toolset must fail")

