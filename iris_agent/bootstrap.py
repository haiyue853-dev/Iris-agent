from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.documents.service import DocumentService
from iris_agent.hot_radar.service import HotRadarService
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
    documents: DocumentService
    hot_radar: HotRadarService
    settings: Settings


def build_application(config_path: str | Path = "agent.yaml") -> ApplicationServices:
    settings = load_settings(config_path)
    client = OpenAI(api_key=settings.llm.api_key or "missing", base_url=settings.llm.base_url, timeout=settings.llm.timeout_seconds)
    provider = OpenAICompatibleProvider(client, settings.llm.model, settings.llm.temperature)
    registry = ToolRegistry()
    factories = {
        "current_time": lambda: build_current_time_tool(),
        "list_directory": lambda: build_list_directory_tool(settings.tools.workspace_root),
        "read_file": lambda: build_read_file_tool(settings.tools.workspace_root, settings.tools.max_read_chars),
    }
    settings.tools.workspace_root.mkdir(parents=True, exist_ok=True)
    for name in settings.tools.enabled:
        if name in factories:
            registry.register(factories[name]())
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
    documents = DocumentService(
        settings.documents.directory,
        provider=provider,
        max_file_bytes=settings.documents.max_file_bytes,
        max_total_bytes=settings.documents.max_total_bytes,
        max_count=settings.documents.max_count,
        max_text_chars=settings.documents.max_text_chars,
    )
    hot_radar = HotRadarService(settings.hot_radar.directory)
    return ApplicationServices(agent, sessions, reports, attachments, skills, documents, hot_radar, settings)
