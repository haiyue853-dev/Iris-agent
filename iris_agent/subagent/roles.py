"""Built-in role templates for focused one-level subagents."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubagentRole:
    key: str
    label: str
    prompt: str
    allowed_tools: tuple[str, ...] | None = None
    max_rounds: int | None = None


SUBAGENT_ROLES: dict[str, SubagentRole] = {
    "general": SubagentRole(
        key="general",
        label="通用",
        prompt="按目标完成任务，只返回与目标直接相关的结论。",
    ),
    "researcher": SubagentRole(
        key="researcher",
        label="资料检索",
        prompt=(
            "你负责资料检索。先明确要回答的问题，再搜索或读取相关资料；"
            "区分事实、推断与不确定信息，保留来源链接，最后给出精炼结论。"
        ),
        allowed_tools=(
            "current_time",
            "web_search",
            "fetch_page",
            "search_knowledge",
            "recall",
            "read_file",
        ),
        max_rounds=6,
    ),
    "knowledge_organizer": SubagentRole(
        key="knowledge_organizer",
        label="知识整理",
        prompt=(
            "你负责知识整理。合并重复信息，提取主题、关键观点、因果和层级关系；"
            "不要把原文逐句拆分，输出结构清晰、可复用的知识摘要。"
        ),
        allowed_tools=("search_knowledge", "recall", "read_file", "use_skill"),
        max_rounds=5,
    ),
    "report_writer": SubagentRole(
        key="report_writer",
        label="报告撰写",
        prompt=(
            "你负责报告撰写。基于已有资料形成有标题、摘要、主体和结论的成稿；"
            "不要虚构资料中不存在的事实，避免展示中间推理过程。"
        ),
        allowed_tools=("search_knowledge", "recall", "read_file", "use_skill"),
        max_rounds=5,
    ),
}


def resolve_subagent_role(role: str | None) -> SubagentRole:
    key = (role or "general").strip().lower()
    template = SUBAGENT_ROLES.get(key)
    if template is None:
        supported = ", ".join(SUBAGENT_ROLES)
        raise ValueError(f"未知子代理角色: {role}；可选角色: {supported}")
    return template


def role_keys() -> tuple[str, ...]:
    return tuple(SUBAGENT_ROLES)
