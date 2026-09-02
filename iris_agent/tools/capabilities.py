from __future__ import annotations

from collections.abc import Mapping, Sequence

from iris_agent.tools.registry import ToolRegistry


class CapabilityResolver:
    def __init__(self, registry: ToolRegistry, toolsets: Mapping[str, Sequence[str]]):
        self.registry = registry
        self.toolsets = {name: tuple(tools) for name, tools in toolsets.items()}

    def resolve(self, enabled: Sequence[str], registry: ToolRegistry | None = None) -> ToolRegistry:
        source = registry or self.registry
        available = set(source.names())
        selected: list[str] = []
        for toolset in enabled:
            if toolset not in self.toolsets:
                raise ValueError(f"unknown toolset: {toolset}")
            for name in self.toolsets[toolset]:
                if name in available and name not in selected:
                    selected.append(name)
        return source.subset(selected)
