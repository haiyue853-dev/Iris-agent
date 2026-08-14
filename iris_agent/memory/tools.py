from dataclasses import asdict

from iris_agent.memory.service import MemoryService
from iris_agent.tools.base import Tool


def build_memory_tools(memory: MemoryService) -> tuple[Tool, Tool]:
    def search_memory(query: str):
        return [asdict(item) for item in memory.search(query)]

    def save_memory(content: str, tags: list[str] | None = None):
        return asdict(memory.remember(content, tags=tuple(tags or ())))

    return (
        Tool("search_memory", "Search user-approved long-term memories relevant to the request.", {
            "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
        }, search_memory),
        Tool("save_memory", "Save a durable user preference or fact for future sessions. Use only when the user explicitly asks to remember it.", {
            "type": "object", "properties": {"content": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["content"],
        }, save_memory, requires_approval=True, approval_context={"effect": "Stores a memory for later sessions"}),
    )
