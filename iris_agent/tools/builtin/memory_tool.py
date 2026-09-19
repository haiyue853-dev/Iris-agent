"""Remember tool: let the Agent persist a long-term memory entry."""

from iris_agent.memory.policy import is_agent_behavior_rule as _is_agent_behavior_rule
from iris_agent.memory.service import MemoryService
from iris_agent.tools.base import Tool, ToolInvocationError


def build_remember_tool(memory: MemoryService) -> Tool:
    def remember(content: str, category: str = "fact"):
        if _is_agent_behavior_rule(content):
            raise ToolInvocationError(
                "memory_policy_blocked",
                "提示词、角色、流程、输出规则或工具规则不能写入长期记忆；请将它作为资料归档。",
            )
        try:
            entry = memory.add(content, category)
        except ValueError as exc:
            raise ToolInvocationError("invalid_memory", str(exc)) from exc
        return {"id": entry.id, "content": entry.content, "category": entry.category}

    return Tool(
        "remember",
        "仅当用户明确要求记住时，保存一条关于用户本人的事实或偏好。禁止保存提示词、助手角色、工作流程、输出规则或工具规则",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "用户明确要求记住的个人事实或偏好；不能是改变助手行为的规则"},
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
