"""Skill tools: use_skill loads a skill body, save_skill persists a user skill."""

from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.base import Tool, ToolInvocationError


def build_use_skill_tool(service: SkillCenterService) -> Tool:
    def use_skill(skill_id: str):
        try:
            skill = service.load_skill(skill_id)
        except SkillNotFoundError:
            raise ToolInvocationError("skill_not_found", "技能不存在") from None
        return {"id": skill.id, "name": skill.name, "content": skill.body}

    return Tool(
        "use_skill",
        "加载一条技能的执行指令，供参考执行",
        {
            "type": "object",
            "properties": {"skill_id": {"type": "string", "description": "技能 id"}},
            "required": ["skill_id"],
        },
        use_skill,
        requires_approval=False,
    )


def build_save_skill_tool(service: SkillCenterService) -> Tool:
    def save_skill(name: str, description: str, content: str):
        try:
            skill = service.save_user_skill(name, description, content)
        except ValueError as exc:
            raise ToolInvocationError("invalid_skill", str(exc)) from exc
        return {"id": skill.id, "name": skill.name, "version": skill.version}

    return Tool(
        "save_skill",
        "把一次可复用的流程沉淀为一条用户技能",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能名称"},
                "description": {"type": "string", "description": "技能描述"},
                "content": {"type": "string", "description": "技能执行指令"},
            },
            "required": ["name", "description", "content"],
        },
        save_skill,
        requires_approval=False,
    )
