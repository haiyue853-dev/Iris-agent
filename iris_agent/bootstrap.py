from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
import atexit
import logging
from typing import Callable

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.automation.service import AutomationService
from iris_agent.notifications.service import NotificationService
from iris_agent.knowledge.embedder import OllamaEmbedder
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import EmbeddingRetriever, HybridRetriever, KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService
from iris_agent.knowledge.rag_service import RagKnowledgeService
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository
from iris_agent.curator.referee import ConflictReferee
from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.service import CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.gateway.service import GatewayService
from iris_agent.gateway.qq import QQOneBotAdapter
from iris_agent.gateway.wecom import WeComAdapter
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import McpToolRefresher, register_mcp_tools
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService as UserProfileService
from iris_agent.settings_profiles import ApiProfile, MigrationDefaults, ProfileStore, ProfileStoreError
from iris_agent.settings_profiles.service import ProfileService as SettingsProfileService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.providers.switchable import SwitchableProvider
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.service import AttachmentService
from iris_agent.attachments.storage import AttachmentStorage
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
from iris_agent.tools.builtin import build_current_time_tool, build_list_directory_tool, build_read_file_tool, build_remember_tool, build_recall_tool, build_use_skill_tool, build_save_skill_tool, build_delegate_task_tool, build_delegate_tasks_tool, build_web_search_tool, build_fetch_page_tool, build_add_knowledge_tool, build_search_knowledge_tool
from iris_agent.web_search.browser_fetcher import BrowserFetcher
from iris_agent.web_search.fetcher import PageFetcher
from iris_agent.web_search.search import WebSearchClient
from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource, TavilySearchSource
from iris_agent.tools.registry import ToolRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    profile: UserProfileService
    knowledge: KnowledgeService
    curator: CuratorService
    mcp: McpCenterService
    mcp_tools: McpToolRefresher
    gateway: GatewayService
    qq_adapter: QQOneBotAdapter | None
    wecom_adapter: WeComAdapter | None
    settings: Settings
    settings_profiles: SettingsProfileService
    chat_attachments: AttachmentService
    _closers: tuple[Callable[[], None], ...] = field(default_factory=tuple, repr=False, compare=False)
    _closed: bool = field(default=False, repr=False, compare=False)

    def close(self) -> None:
        if self._closed:
            return
        object.__setattr__(self, "_closed", True)
        first_error: Exception | None = None
        for closer in reversed(self._closers):
            try:
                closer()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


def build_application(config_path: str | Path = "agent.yaml") -> ApplicationServices:
    resource_closers: list[Callable[[], None]] = []
    try:
        return _build_application(config_path, resource_closers)
    except Exception:
        for closer in reversed(resource_closers):
            try:
                closer()
            except Exception:
                pass
        raise


def _build_application(
    config_path: str | Path,
    resource_closers: list[Callable[[], None]],
) -> ApplicationServices:
    settings = load_settings(config_path)
    profile_store = ProfileStore(
        PROJECT_ROOT / "data" / "settings_profiles.json",
        PROJECT_ROOT / ".env",
        MigrationDefaults(settings.llm.base_url, settings.llm.model, settings.llm.api_key),
    )

    def make_provider(value: ApiProfile) -> OpenAICompatibleProvider:
        client = OpenAI(api_key=value.api_key or "local-no-key", base_url=value.base_url, timeout=settings.llm.timeout_seconds)
        return OpenAICompatibleProvider(client, value.model, settings.llm.temperature)

    try:
        profile_collection = profile_store.load()
        active_profile = next(item for item in profile_collection.profiles if item.id == profile_collection.active_id)
        provider = make_provider(active_profile)
    except ProfileStoreError:
        logging.getLogger(__name__).warning("Settings profile store unavailable; using configured LLM fallback")
        client = OpenAI(api_key=settings.llm.api_key or "missing", base_url=settings.llm.base_url, timeout=settings.llm.timeout_seconds)
        provider = OpenAICompatibleProvider(client, settings.llm.model, settings.llm.temperature)
    provider_handle = SwitchableProvider(provider)
    resource_closers.append(provider_handle.close)
    provider = provider_handle
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
    profile = UserProfileService(
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
    settings_profiles = SettingsProfileService(profile_store, make_provider, provider_handle.replace, provider_handle.current)
    agent = AgentService(loop, sessions, settings.agent.system_prompt, memory=memory, profile_service=profile, compressor=compressor, knowledge=None)
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
    chat_attachments = AttachmentService(
        AttachmentStorage(
            settings.attachments.directory,
            settings.attachments.max_file_bytes,
            settings.attachments.max_total_bytes,
            settings.attachments.max_count,
            temporary_ttl=timedelta(seconds=settings.attachments.temporary_ttl_seconds),
        ),
        sessions,
        LocalAttachmentExtractor(settings.attachments.max_text_chars),
    )
    agent.attachment_service = chat_attachments
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
        max_parallel_tasks=settings.subagent.max_parallel_tasks,
    )
    registry.register(build_delegate_task_tool(subagent))
    registry.register(build_delegate_tasks_tool(subagent))
    search_sources = []
    if settings.web_search.enable_tavily and settings.web_search.tavily_api_key:
        tavily_source = TavilySearchSource(
            api_key=settings.web_search.tavily_api_key,
            timeout=settings.web_search.timeout_seconds,
            max_snippet_chars=settings.web_search.max_snippet_chars,
        )
        search_sources.append(tavily_source)
        resource_closers.append(tavily_source.close)
    bing_source = BingSearchSource(
        timeout=settings.web_search.timeout_seconds,
        max_snippet_chars=settings.web_search.max_snippet_chars,
    )
    search_sources.append(bing_source)
    resource_closers.append(bing_source.close)
    if settings.web_search.enable_duckduckgo:
        duckduckgo_source = DuckDuckGoSearchSource(
            timeout=settings.web_search.timeout_seconds,
            max_snippet_chars=settings.web_search.max_snippet_chars,
        )
        search_sources.append(duckduckgo_source)
        resource_closers.append(duckduckgo_source.close)
    web_search_client = WebSearchClient(
        timeout=settings.web_search.timeout_seconds,
        max_results=settings.web_search.max_results,
        max_snippet_chars=settings.web_search.max_snippet_chars,
        enabled=settings.web_search.enabled,
        sources=search_sources,
        max_retries=settings.web_search.max_retries,
    )
    browser_fetcher = None
    if settings.web_search.enable_browser_fallback:
        browser_fetcher = BrowserFetcher(
            channel=settings.web_search.browser_channel,
            timeout=settings.web_search.timeout_seconds,
            max_page_chars=settings.web_search.max_page_chars,
            max_download_bytes=settings.web_search.max_download_bytes,
        )
    page_fetcher = PageFetcher(
        timeout=settings.web_search.timeout_seconds,
        max_page_chars=settings.web_search.max_page_chars,
        max_download_bytes=settings.web_search.max_download_bytes,
        enabled=settings.web_search.enabled,
        max_retries=settings.web_search.max_retries,
        min_text_chars=settings.web_search.min_text_chars,
        browser_fetcher=browser_fetcher,
    )
    resource_closers.append(page_fetcher.close)
    registry.register(build_web_search_tool(
        web_search_client,
        default_search_depth=settings.web_search.default_search_depth,
    ))
    registry.register(build_fetch_page_tool(page_fetcher))
    rag_embedder = OllamaEmbedder(model=settings.knowledge.embedding_model,
                                  base_url=settings.knowledge.embedding_base_url,
                                  timeout=settings.knowledge.embedding_timeout_seconds)
    knowledge = RagKnowledgeService(
        SqliteKnowledgeRepository(settings.knowledge.database_file), embedder=rag_embedder,
        files_directory=settings.knowledge.files_directory, chunk_target_chars=settings.knowledge.chunk_target_chars,
        chunk_overlap_chars=settings.knowledge.chunk_overlap_chars, embedding_batch_size=settings.knowledge.embedding_batch_size,
        retrieval_limit=settings.knowledge.retrieval_limit, max_context_chars=settings.knowledge.max_context_chars,
        minimum_relevance_score=settings.knowledge.minimum_relevance_score, max_file_bytes=settings.knowledge.max_file_bytes,
        max_total_bytes=settings.knowledge.max_total_bytes, max_document_count=settings.knowledge.max_document_count,
        allowed_extensions=settings.knowledge.allowed_upload_extensions,
    )
    agent.knowledge = knowledge
    curator_embedder = OllamaEmbedder(
        model=settings.knowledge.embedding_model,
        base_url=settings.knowledge.embedding_base_url,
        timeout=settings.knowledge.embedding_timeout_seconds,
    )
    curator = CuratorService(
        CuratorRepository(settings.curator.directory, max_reports=settings.curator.max_reports),
        memory,
        profile,
        SimilarityEngine(
            curator_embedder,
            merge_threshold=settings.curator.merge_threshold,
            conflict_threshold=settings.curator.conflict_threshold,
        ),
        skills=skills,
        knowledge=None,
        referee=ConflictReferee(provider),
        enable_llm=settings.curator.enable_llm,
        max_pairs_per_run=settings.curator.max_pairs_per_run,
        expire_days=settings.curator.expire_days,
        consolidate_enabled=settings.curator.consolidate_enabled,
        consolidate_min_entries=settings.curator.consolidate_min_entries,
    )
    hot_radar = HotRadarService(settings.hot_radar.directory)
    notifications = NotificationService(settings.notifications.directory)
    automation = AutomationService(settings.automation.directory, hot_radar, notifications)
    task_center = TaskCenterService(settings.task_center.directory)
    task_queue = TaskQueueService(agent, task_center, QueueRepository(settings.task_queue.directory))
    gateway = GatewayService(
        agent,
        sessions,
        session_prefix=settings.gateway.session_prefix,
        state_file=settings.gateway.directory / "sessions.json",
    )
    qq_adapter = (
        QQOneBotAdapter(
            gateway,
            respond_groups=settings.gateway.qq.respond_groups,
            allowed_users=settings.gateway.qq.allowed_users,
            allow_all=settings.gateway.qq.allow_all,
        )
        if settings.gateway.qq.enabled
        else None
    )
    wecom_adapter = None
    if settings.gateway.wecom.enabled:
        wecom_adapter = WeComAdapter(
            gateway,
            corp_id=settings.gateway.wecom.corp_id,
            agent_id=settings.gateway.wecom.agent_id,
            secret=settings.gateway.wecom.secret,
            token=settings.gateway.wecom.token,
            aes_key=settings.gateway.wecom.aes_key,
        )
    if settings.gateway.push.enabled and qq_adapter is not None and settings.gateway.push.qq_target:
        qq_target = settings.gateway.push.qq_target

        def _push(text: str) -> None:
            qq_adapter.push_text(qq_target, text)

        automation.push = _push
    return ApplicationServices(agent, sessions, reports, attachments, skills, hot_radar, automation, notifications, task_center, task_queue, memory, session_search, subagent, profile, knowledge, curator, mcp, mcp_tools, gateway, qq_adapter, wecom_adapter, settings, settings_profiles, chat_attachments, tuple(resource_closers))
