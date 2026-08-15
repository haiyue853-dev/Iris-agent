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
    system_prompt: str = "你是 Iris Agent，一个智能助手。始终使用中文与用户交流。"
    max_tool_rounds: int = 8


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
    user_directory: Path = Path("data/skills/user")
    max_body_chars: int = 4000


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
class TaskQueueSettings:
    directory: Path = Path("data/task_queue")


@dataclass(slots=True)
class MemorySettings:
    directory: Path = Path("data/memory")
    max_entries: int = 500
    max_chars: int = 500
    max_injected_chars: int = 2000
    max_injected_entries: int = 20


@dataclass(slots=True)
class SessionSearchSettings:
    max_hit_chars: int = 300
    default_limit: int = 5


@dataclass(slots=True)
class SubagentSettings:
    max_goal_chars: int = 2000
    max_context_chars: int = 4000
    max_result_chars: int = 4000
    default_max_rounds: int = 6
    allowed_tools: list[str] = field(
        default_factory=lambda: ["current_time", "list_directory", "read_file", "recall", "use_skill"]
    )


@dataclass(slots=True)
class ProfileSettings:
    directory: Path = Path("data/profile")
    max_items_per_field: int = 20
    max_item_chars: int = 200
    extract_interval_rounds: int = 10
    enabled: bool = True


@dataclass(slots=True)
class ContextSettings:
    trigger_chars: int = 12000
    keep_recent: int = 10
    max_summary_chars: int = 2000
    enabled: bool = True


@dataclass(slots=True)
class WebSearchSettings:
    enabled: bool = True
    timeout_seconds: float = 15
    max_results: int = 5
    max_snippet_chars: int = 300
    max_page_chars: int = 30000
    max_retries: int = 2
    enable_duckduckgo: bool = False
    enable_browser_fallback: bool = False
    browser_channel: str = "msedge"
    min_text_chars: int = 200


@dataclass(slots=True)
class KnowledgeSettings:
    directory: Path = Path("data/knowledge")
    max_content_chars: int = 50000
    max_hit_chars: int = 500
    default_limit: int = 5
    retriever: str = "keyword"
    embedding_model: str = "bge-m3"
    embedding_base_url: str = "http://localhost:11434"
    embedding_timeout_seconds: float = 60


@dataclass(slots=True)
class McpSettings:
    settings_file: Path = Path("data/mcp/servers.json")


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
    task_queue: TaskQueueSettings = field(default_factory=TaskQueueSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    session_search: SessionSearchSettings = field(default_factory=SessionSearchSettings)
    subagent: SubagentSettings = field(default_factory=SubagentSettings)
    profile: ProfileSettings = field(default_factory=ProfileSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    web_search: WebSearchSettings = field(default_factory=WebSearchSettings)
    knowledge: KnowledgeSettings = field(default_factory=KnowledgeSettings)
    mcp: McpSettings = field(default_factory=McpSettings)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigurationError(f"配置节 {name} 必须是对象")
    return value


def _split_tools(value: Any) -> list[str]:
    if value is None:
        return SubagentSettings().allowed_tools
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return parts if parts else SubagentSettings().allowed_tools
    return SubagentSettings().allowed_tools


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
    task_queue = _section(raw, "task_queue")
    memory = _section(raw, "memory")
    session_search = _section(raw, "session_search")
    subagent = _section(raw, "subagent")
    profile = _section(raw, "profile")
    context = _section(raw, "context")
    web_search = _section(raw, "web_search")
    knowledge = _section(raw, "knowledge")
    mcp = _section(raw, "mcp")
    model = overrides.get("model") or os.getenv("LLM_MODEL") or llm.get("model", "deepseek-chat")
    base_url = overrides.get("base_url") or os.getenv("OPENAI_BASE_URL") or llm.get("base_url", "https://api.deepseek.com/v1")
    api_key = overrides.get("api_key") or os.getenv("OPENAI_API_KEY", "")
    settings = Settings(
        llm=LLMSettings(
            provider=str(llm.get("provider", "openai_compatible")), model=str(model),
            base_url=str(base_url), api_key=str(api_key),
            temperature=float(llm.get("temperature", 0.2)), timeout_seconds=float(llm.get("timeout_seconds", 60)),
        ),
        agent=AgentSettings(system_prompt=str(agent.get("system_prompt", raw.get("system_prompt", AgentSettings().system_prompt))), max_tool_rounds=int(agent.get("max_tool_rounds", 8))),
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
            user_directory=Path(skills.get("user_directory", "data/skills/user")),
            max_body_chars=int(skills.get("max_body_chars", 4000)),
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
        task_queue=TaskQueueSettings(directory=Path(task_queue.get("directory", "data/task_queue"))),
        memory=MemorySettings(
            directory=Path(memory.get("directory", "data/memory")),
            max_entries=int(memory.get("max_entries", 500)),
            max_chars=int(memory.get("max_chars", 500)),
            max_injected_chars=int(memory.get("max_injected_chars", 2000)),
            max_injected_entries=int(memory.get("max_injected_entries", 20)),
        ),
        session_search=SessionSearchSettings(
            max_hit_chars=int(session_search.get("max_hit_chars", 300)),
            default_limit=int(session_search.get("default_limit", 5)),
        ),
        subagent=SubagentSettings(
            max_goal_chars=int(subagent.get("max_goal_chars", 2000)),
            max_context_chars=int(subagent.get("max_context_chars", 4000)),
            max_result_chars=int(subagent.get("max_result_chars", 4000)),
            default_max_rounds=int(subagent.get("default_max_rounds", 6)),
            allowed_tools=_split_tools(subagent.get("allowed_tools")),
        ),
        profile=ProfileSettings(
            directory=Path(profile.get("directory", "data/profile")),
            max_items_per_field=int(profile.get("max_items_per_field", 20)),
            max_item_chars=int(profile.get("max_item_chars", 200)),
            extract_interval_rounds=int(profile.get("extract_interval_rounds", 10)),
            enabled=bool(profile.get("enabled", True)),
        ),
        context=ContextSettings(
            trigger_chars=int(context.get("trigger_chars", 12000)),
            keep_recent=int(context.get("keep_recent", 10)),
            max_summary_chars=int(context.get("max_summary_chars", 2000)),
            enabled=bool(context.get("enabled", True)),
        ),
        web_search=WebSearchSettings(
            enabled=bool(web_search.get("enabled", True)),
            timeout_seconds=float(web_search.get("timeout_seconds", 15)),
            max_results=int(web_search.get("max_results", 5)),
            max_snippet_chars=int(web_search.get("max_snippet_chars", 300)),
            max_page_chars=int(web_search.get("max_page_chars", 30000)),
            max_retries=int(web_search.get("max_retries", 2)),
            enable_duckduckgo=bool(web_search.get("enable_duckduckgo", False)),
            enable_browser_fallback=bool(web_search.get("enable_browser_fallback", False)),
            browser_channel=str(web_search.get("browser_channel", "msedge")),
            min_text_chars=int(web_search.get("min_text_chars", 200)),
        ),
        knowledge=KnowledgeSettings(
            directory=Path(knowledge.get("directory", "data/knowledge")),
            max_content_chars=int(knowledge.get("max_content_chars", 50000)),
            max_hit_chars=int(knowledge.get("max_hit_chars", 500)),
            default_limit=int(knowledge.get("default_limit", 5)),
            retriever=str(knowledge.get("retriever", "keyword")),
            embedding_model=str(knowledge.get("embedding_model", "bge-m3")),
            embedding_base_url=str(knowledge.get("embedding_base_url", "http://localhost:11434")),
            embedding_timeout_seconds=float(knowledge.get("embedding_timeout_seconds", 60)),
        ),
        mcp=McpSettings(settings_file=Path(mcp.get("settings_file", "data/mcp/servers.json"))),
    )
    if not settings.llm.model.strip() or settings.agent.max_tool_rounds < 1:
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
