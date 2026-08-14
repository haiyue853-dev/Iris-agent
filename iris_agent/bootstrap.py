from dataclasses import dataclass
from pathlib import Path
import atexit

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository
from iris_agent.automation.service import AutomationService
from iris_agent.notifications.service import NotificationService
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import McpToolRefresher, register_mcp_tools
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.base import SessionRepository
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.tools.builtin import build_current_time_tool, build_list_directory_tool, build_read_file_tool
from iris_agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    agent: AgentService
    sessions: SessionRepository
    reports: DailyReportService
    attachments: AttachmentRepository
    skills: SkillCenterService
    hot_radar: HotRadarService
    automation: AutomationService
    notifications: NotificationService
    mcp: McpCenterService
    mcp_tools: McpToolRefresher
    interview_knowledge: InterviewKnowledgeRepository
    settings: Settings


def build_application(config_path: str | Path = "agent.yaml") -> ApplicationServices:
    settings = load_settings(config_path)
    client = OpenAI(api_key=settings.llm.api_key or "missing", base_url=settings.llm.base_url, timeout=settings.llm.timeout_seconds)
    provider = OpenAICompatibleProvider(client, settings.llm.model, settings.llm.temperature)
    registry = ToolRegistry()
    interview_knowledge = InterviewKnowledgeRepository(settings.interview_knowledge.path)
    factories = {
        "current_time": lambda: build_current_time_tool(),
        "list_directory": lambda: build_list_directory_tool(settings.tools.workspace_root),
        "read_file": lambda: build_read_file_tool(settings.tools.workspace_root, settings.tools.max_read_chars),
    }
    settings.tools.workspace_root.mkdir(parents=True, exist_ok=True)
    for name in settings.tools.enabled:
        if name in factories:
            registry.register(factories[name]())
    mcp = McpCenterService(settings.mcp.settings_file)
    mcp.ensure_builtin_interview_server(settings.interview_knowledge.path)
    atexit.register(mcp.close)
    register_mcp_tools(registry, mcp, cached_only=True)
    mcp_tools = McpToolRefresher(registry, mcp)
    mcp_tools.refresh()
    sessions = JsonSessionRepository(settings.sessions.directory)
    loop = AgentLoop(provider, registry, settings.agent.max_tool_rounds)
    agent = AgentService(loop, sessions, settings.agent.system_prompt)
    report_repository = JsonDailyReportRepository(
        settings.reports.directory,
        max_versions=settings.reports.max_versions,
    )
    reports = DailyReportService(
        provider,
        sessions,
        report_repository,
        max_input_chars=settings.reports.max_input_chars,
        max_revision_chars=settings.reports.max_revision_chars,
    )
    attachments = AttachmentRepository(
        settings.reports.attachments_directory,
        max_file_bytes=settings.reports.max_attachment_bytes,
        max_total_bytes=settings.reports.max_attachment_total_bytes,
        max_count=settings.reports.max_attachment_count,
    )
    skills = SkillCenterService(
        Path(__file__).parent / "skill_center" / "bundled",
        settings.skills.settings_file,
    )
    hot_radar = HotRadarService(settings.hot_radar.directory)
    notifications = NotificationService(settings.notifications.directory)
    automation = AutomationService(settings.automation.directory, hot_radar, notifications)
    return ApplicationServices(agent, sessions, reports, attachments, skills, hot_radar, automation, notifications, mcp, mcp_tools, interview_knowledge, settings)
