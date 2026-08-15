"""Remember tool: let the Agent persist a long-term memory entry."""

from iris_agent.memory.service import MemoryService
from iris_agent.tools.base import Tool, ToolInvocationError


def build_remember_tool(memory: MemoryService) -> Tool:
    def remember(content: str, category: str = "fact"):
        try:
            entry = memory.add(content, category)
        except ValueError as exc:
            raise ToolInvocationError("invalid_memory", str(exc)) from exc
        return {"id": entry.id, "content": entry.content, "category": entry.category}

    return Tool(
        "remember",
        "记住一条关于用户的长期信息，供后续对话使用",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要记住的内容"},
                "category": {
                    "type": "string",
                    "enum": ["preference", "fact", "project", "other"],
                    "description": "记忆类别",
                },
            },
            "required": ["content"],
        },
        remember,
        requires_approval=False,
    )
