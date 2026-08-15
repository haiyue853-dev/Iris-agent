from dataclasses import dataclass
from pathlib import Path
import atexit

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.automation.service import AutomationService
from iris_agent.notifications.service import NotificationService
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import McpToolRefresher, register_mcp_tools
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.session_search.service import SessionSearchService
from iris_agent.sessions.base import SessionRepository
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.subagent.runner import SubagentRunner
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.repository import QueueRepository
from iris_agent.task_queue.service import TaskQueueService
from iris_agent.tools.builtin import build_current_time_tool, build_list_directory_tool, build_read_file_tool, build_remember_tool, build_recall_tool, build_use_skill_tool, build_save_skill_tool, build_delegate_task_tool, build_web_search_tool, build_fetch_page_tool
from iris_agent.web_search.fetcher import PageFetcher
from iris_agent.web_search.search import WebSearchClient
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
    task_center: TaskCenterService
    task_queue: TaskQueueService
    memory: MemoryService
    session_search: SessionSearchService
    subagent: SubagentRunner
    profile: ProfileService
    mcp: McpCenterService
    mcp_tools: McpToolRefresher
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
    mcp = McpCenterService(settings.mcp.settings_file)
    atexit.register(mcp.close)
    register_mcp_tools(registry, mcp, cached_only=True)
    mcp_tools = McpToolRefresher(registry, mcp)
    sessions = JsonSessionRepository(settings.sessions.directory)
    memory = MemoryService(
        MemoryRepository(settings.memory.directory),
        max_entries=settings.memory.max_entries,
        max_chars=settings.memory.max_chars,
        max_injected_chars=settings.memory.max_injected_chars,
        max_injected_entries=settings.memory.max_injected_entries,
    )
    registry.register(build_remember_tool(memory))
    session_search = SessionSearchService(
        sessions,
        max_hit_chars=settings.session_search.max_hit_chars,
        default_limit=settings.session_search.default_limit,
    )
    registry.register(build_recall_tool(session_search))
    profile = ProfileService(
        ProfileRepository(settings.profile.directory),
        ProfileExtractor(provider),
        max_items_per_field=settings.profile.max_items_per_field,
        max_item_chars=settings.profile.max_item_chars,
        extract_interval_rounds=settings.profile.extract_interval_rounds,
        enabled=settings.profile.enabled,
    )
    compressor = ContextCompressor(
        provider,
        trigger_chars=settings.context.trigger_chars,
        keep_recent=settings.context.keep_recent,
        max_summary_chars=settings.context.max_summary_chars,
        enabled=settings.context.enabled,
    )
    loop = AgentLoop(provider, registry, settings.agent.max_tool_rounds)
    agent = AgentService(loop, sessions, settings.agent.system_prompt, memory=memory, profile_service=profile, compressor=compressor)
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
        user_directory=settings.skills.user_directory,
        max_body_chars=settings.skills.max_body_chars,
    )
    registry.register(build_use_skill_tool(skills))
    registry.register(build_save_skill_tool(skills))
    subagent = SubagentRunner(
        provider,
        registry.subset,
        "你是主 Agent 委派的子代理，负责独立完成一个子任务。专注于任务目标，完成后把最终结论作为回复返回。始终使用中文。",
        max_goal_chars=settings.subagent.max_goal_chars,
        max_context_chars=settings.subagent.max_context_chars,
        max_result_chars=settings.subagent.max_result_chars,
        default_max_rounds=settings.subagent.default_max_rounds,
        default_allowed_tools=settings.subagent.allowed_tools,
    )
    registry.register(build_delegate_task_tool(subagent))
    web_search_client = WebSearchClient(
        timeout=settings.web_search.timeout_seconds,
        max_results=settings.web_search.max_results,
        max_snippet_chars=settings.web_search.max_snippet_chars,
        enabled=settings.web_search.enabled,
    )
    page_fetcher = PageFetcher(
        timeout=settings.web_search.timeout_seconds,
        max_page_chars=settings.web_search.max_page_chars,
        enabled=settings.web_search.enabled,
    )
    registry.register(build_web_search_tool(web_search_client))
    registry.register(build_fetch_page_tool(page_fetcher))
    hot_radar = HotRadarService(settings.hot_radar.directory)
    notifications = NotificationService(settings.notifications.directory)
    automation = AutomationService(settings.automation.directory, hot_radar, notifications)
    task_center = TaskCenterService(settings.task_center.directory)
    task_queue = TaskQueueService(agent, task_center, QueueRepository(settings.task_queue.directory))
    return ApplicationServices(agent, sessions, reports, attachments, skills, hot_radar, automation, notifications, task_center, task_queue, memory, session_search, subagent, profile, mcp, mcp_tools, settings)
