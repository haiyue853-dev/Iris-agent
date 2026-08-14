from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

from iris_agent.core.errors import ConfigurationError


@dataclass(slots=True)
class LLMSettings:
    provider: str = "openai_compatible"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    temperature: float = 0.2
    timeout_seconds: float = 60.0


@dataclass(slots=True)
class AgentSettings:
    system_prompt: str = "你是 Iris Agent，一个智能助手。始终使用中文与用户交流。需要调用工具时，先用一句简短的话说明计划；基于工具返回的结果继续行动，并在完成后给出直接、可验证的结论。"
    max_tool_rounds: int = 8
    max_context_chars: int = 80_000


@dataclass(slots=True)
class SessionSettings:
    directory: Path = Path("data/sessions")


@dataclass(slots=True)
class ReportSettings:
    directory: Path = Path("data/reports")
    attachments_directory: Path = Path("data/report_attachments")
    max_input_chars: int = 50_000
    max_revision_chars: int = 2_000
    max_versions: int = 20
    max_attachment_bytes: int = 10_000_000
    max_attachment_total_bytes: int = 50_000_000
    max_attachment_count: int = 10
    max_attachment_text_chars: int = 20_000


@dataclass(slots=True)
class ToolSettings:
    enabled: list[str] = field(default_factory=lambda: ["current_time", "list_directory", "read_file"])
    workspace_root: Path = Path("workspace")
    max_read_chars: int = 20_000


@dataclass(slots=True)
class SkillSettings:
    directory: Path = Path("data/skills")
    settings_file: Path = Path("data/skills/settings.json")


@dataclass(slots=True)
class HotRadarSettings:
    directory: Path = Path("data/hot_radar")
    poll_interval_seconds: int = 60
    timezone: str = "Asia/Shanghai"


@dataclass(slots=True)
class AutomationSettings:
    directory: Path = Path("data/automation")


@dataclass(slots=True)
class NotificationSettings:
    directory: Path = Path("data/notifications")


@dataclass(slots=True)
class TaskCenterSettings:
    directory: Path = Path("data/tasks")


@dataclass(slots=True)
class McpSettings:
    settings_file: Path = Path("data/mcp/servers.json")


@dataclass(slots=True)
class InterviewKnowledgeSettings:
    path: Path = Path("data/interview_knowledge.json")


@dataclass(slots=True)
class TaskPlanningSettings:
    directory: Path = Path("data/task_plans")


@dataclass(slots=True)
class MemorySettings:
    directory: Path = Path("data/memory")
    enabled: bool = False
    max_results: int = 4


@dataclass(slots=True)
class SubagentSettings:
    directory: Path = Path("data/subagents")
    max_concurrent: int = 2
    max_tool_rounds: int = 4


@dataclass(slots=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    sessions: SessionSettings = field(default_factory=SessionSettings)
    reports: ReportSettings = field(default_factory=ReportSettings)
    tools: ToolSettings = field(default_factory=ToolSettings)
    skills: SkillSettings = field(default_factory=SkillSettings)
    hot_radar: HotRadarSettings = field(default_factory=HotRadarSettings)
    automation: AutomationSettings = field(default_factory=AutomationSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    task_center: TaskCenterSettings = field(default_factory=TaskCenterSettings)
    mcp: McpSettings = field(default_factory=McpSettings)
    interview_knowledge: InterviewKnowledgeSettings = field(default_factory=InterviewKnowledgeSettings)
    task_planning: TaskPlanningSettings = field(default_factory=TaskPlanningSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    subagents: SubagentSettings = field(default_factory=SubagentSettings)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigurationError(f"配置节 {name} 必须是对象")
    return value


def load_settings(config_path: str | Path = "agent.yaml", **overrides: Any) -> Settings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"无法读取配置文件: {exc}") from exc
    llm = _section(raw, "llm")
    agent = _section(raw, "agent")
    sessions = _section(raw, "sessions")
    reports = _section(raw, "reports")
    tools = _section(raw, "tools")
    skills = _section(raw, "skills")
    hot_radar = _section(raw, "hot_radar")
    automation = _section(raw, "automation")
    notifications = _section(raw, "notifications")
    task_center = _section(raw, "task_center")
    mcp = _section(raw, "mcp")
    interview_knowledge = _section(raw, "interview_knowledge")
    task_planning = _section(raw, "task_planning")
    memory = _section(raw, "memory")
    subagents = _section(raw, "subagents")
    model = overrides.get("model") or os.getenv("LLM_MODEL") or llm.get("model", "deepseek-chat")
    base_url = overrides.get("base_url") or os.getenv("OPENAI_BASE_URL") or llm.get("base_url", "https://api.deepseek.com/v1")
    api_key = overrides.get("api_key") or os.getenv("OPENAI_API_KEY", "")
    settings = Settings(
        llm=LLMSettings(
            provider=str(llm.get("provider", "openai_compatible")), model=str(model),
            base_url=str(base_url), api_key=str(api_key),
            temperature=float(llm.get("temperature", 0.2)), timeout_seconds=float(llm.get("timeout_seconds", 60)),
        ),
        agent=AgentSettings(system_prompt=str(agent.get("system_prompt", raw.get("system_prompt", AgentSettings().system_prompt))), max_tool_rounds=int(agent.get("max_tool_rounds", 8)), max_context_chars=int(agent.get("max_context_chars", 80_000))),
        sessions=SessionSettings(directory=Path(sessions.get("directory", raw.get("session_path", "data/sessions")))),
        reports=ReportSettings(
            directory=Path(reports.get("directory", "data/reports")),
            attachments_directory=Path(reports.get("attachments_directory", "data/report_attachments")),
            max_input_chars=int(reports.get("max_input_chars", 50_000)),
            max_revision_chars=int(reports.get("max_revision_chars", 2_000)),
            max_versions=int(reports.get("max_versions", 20)),
            max_attachment_bytes=int(reports.get("max_attachment_bytes", 10_000_000)),
            max_attachment_total_bytes=int(reports.get("max_attachment_total_bytes", 50_000_000)),
            max_attachment_count=int(reports.get("max_attachment_count", 10)),
            max_attachment_text_chars=int(reports.get("max_attachment_text_chars", 20_000)),
        ),
        tools=ToolSettings(enabled=list(tools.get("enabled", ToolSettings().enabled)), workspace_root=Path(tools.get("workspace_root", "workspace")), max_read_chars=int(tools.get("max_read_chars", 20_000))),
        skills=SkillSettings(
            directory=Path(skills.get("directory", "data/skills")),
            settings_file=Path(skills.get("settings_file", str(Path(str(skills.get("directory", "data/skills"))) / "settings.json"))),
        ),
        hot_radar=HotRadarSettings(
            directory=Path(hot_radar.get("directory", "data/hot_radar")),
            poll_interval_seconds=int(hot_radar.get("poll_interval_seconds", 60)),
            timezone=str(hot_radar.get("timezone", "Asia/Shanghai")),
        ),
        automation=AutomationSettings(
            directory=Path(automation.get("directory", "data/automation")),
        ),
        notifications=NotificationSettings(
            directory=Path(notifications.get("directory", "data/notifications")),
        ),
        task_center=TaskCenterSettings(directory=Path(task_center.get("directory", "data/tasks"))),
        mcp=McpSettings(settings_file=Path(mcp.get("settings_file", "data/mcp/servers.json"))),
        interview_knowledge=InterviewKnowledgeSettings(path=Path(interview_knowledge.get("path", "data/interview_knowledge.json"))),
        task_planning=TaskPlanningSettings(directory=Path(task_planning.get("directory", "data/task_plans"))),
        memory=MemorySettings(directory=Path(memory.get("directory", "data/memory")), enabled=bool(memory.get("enabled", False)), max_results=int(memory.get("max_results", 4))),
        subagents=SubagentSettings(directory=Path(subagents.get("directory", "data/subagents")), max_concurrent=int(subagents.get("max_concurrent", 2)), max_tool_rounds=int(subagents.get("max_tool_rounds", 4))),
    )
    if not settings.llm.model.strip() or settings.agent.max_tool_rounds < 1 or settings.agent.max_context_chars < 1_000 or not 1 <= settings.memory.max_results <= 10 or settings.subagents.max_concurrent < 1 or settings.subagents.max_tool_rounds < 1:
        raise ConfigurationError("模型名称不能为空，且 max_tool_rounds 必须大于 0")
    if (
        settings.reports.max_input_chars < 1
        or settings.reports.max_revision_chars < 1
        or settings.reports.max_versions < 1
        or settings.reports.max_attachment_bytes < 1
        or settings.reports.max_attachment_total_bytes < 1
        or settings.reports.max_attachment_count < 1
        or settings.reports.max_attachment_text_chars < 1
    ):
        raise ConfigurationError("日报输入限制和版本上限必须大于 0")
    if (
        settings.hot_radar.poll_interval_seconds < 1
    ):
        raise ConfigurationError("热点雷达轮询间隔必须大于 0")
    return settings
