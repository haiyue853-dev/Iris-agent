from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
import atexit
import logging
import os
from typing import Callable

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.automation.service import AutomationService
from iris_agent.notifications.service import NotificationService
from iris_agent.knowledge.embedder import OllamaEmbedder
from iris_agent.knowledge.extractor import OllamaGraphExtractor
from iris_agent.knowledge.semantic_splitter import LocalSemanticSplitter
from iris_agent.knowledge.parsing import OllamaImageDescriber
from iris_agent.knowledge.reranking import build_reranker
from iris_agent.knowledge.runtime_config import load_runtime_config
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import EmbeddingRetriever, HybridRetriever, KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService
from iris_agent.knowledge.rag_service import RagKnowledgeService
from iris_agent.knowledge.orchestrator import KnowledgeOrchestrator
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository
from iris_agent.curator.referee import ConflictReferee
from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.service import CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.gateway.service import GatewayService
from iris_agent.gateway.qq import QQOneBotAdapter
from iris_agent.gateway.napcat import NapCatLauncher
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
from iris_agent.subagent.delegation import DelegationRepository, DelegationService
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.repository import QueueRepository
from iris_agent.task_queue.service import TaskQueueService
from iris_agent.tools.builtin import build_current_time_tool, build_list_directory_tool, build_read_file_tool, build_replace_in_file_tool, build_run_command_tool, build_write_file_tool, build_remember_tool, build_recall_tool, build_use_skill_tool, build_save_skill_tool, build_delegate_task_tool, build_delegate_tasks_tool, build_delegate_workflow_tool, build_request_subagent_collaboration_tool, build_web_search_tool, build_fetch_page_tool, build_collect_interview_knowledge_tool, build_add_knowledge_tool, build_search_knowledge_tool
from iris_agent.web_search.browser_fetcher import BrowserFetcher
from iris_agent.web_search.fetcher import PageFetcher
from iris_agent.web_search.search import WebSearchClient
from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource, TavilySearchSource
from iris_agent.web_search.summarizer import PageSummarizer
from iris_agent.tools.registry import ToolRegistry
from iris_agent.tools.capabilities import CapabilityResolver

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rag_runtime_defaults(settings: Settings) -> dict[str, object]:
    return {
        "embedding_enabled": True,
        "embedding_model": settings.knowledge.embedding_model,
        "embedding_base_url": settings.knowledge.embedding_base_url,
        "semantic_split_enabled": settings.knowledge.semantic_split_enabled,
        "semantic_split_model": settings.knowledge.semantic_split_model,
        "semantic_split_base_url": settings.knowledge.semantic_split_base_url,
        "graph_enabled": settings.knowledge.graph_extraction_enabled,
        "graph_model": settings.knowledge.graph_extraction_model,
        "graph_base_url": settings.knowledge.graph_extraction_base_url,
        "image_enabled": settings.knowledge.image_parsing_enabled,
        "image_model": settings.knowledge.image_parsing_model,
        "image_base_url": settings.knowledge.image_parsing_base_url,
        "reranker_enabled": settings.knowledge.reranker_enabled,
        "reranker_provider": settings.knowledge.reranker_provider,
        "reranker_model": settings.knowledge.reranker_model,
        "reranker_base_url": settings.knowledge.reranker_base_url,
        "mmr_relevance_weight": 0.7,
    }


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
    napcat: NapCatLauncher
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
        "write_file": lambda: build_write_file_tool(settings.tools.workspace_root),
        "replace_in_file": lambda: build_replace_in_file_tool(settings.tools.workspace_root),
        "run_command": lambda: build_run_command_tool(settings.tools.workspace_root, timeout_seconds=settings.tools.command_timeout_seconds, max_output_chars=settings.tools.command_max_output_chars, allowed_commands=settings.tools.allowed_commands),
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
        trigger_tokens=settings.context.trigger_tokens,
        keep_recent=settings.context.keep_recent,
        max_summary_chars=settings.context.max_summary_chars,
        enabled=settings.context.enabled,
    )
    loop = AgentLoop(provider, registry, settings.agent.max_tool_rounds)
    settings_profiles = SettingsProfileService(profile_store, make_provider, provider_handle.replace, provider_handle.current)
    def resolve_model_profile(profile_id: str):
        try:
            collection = profile_store.load()
        except ProfileStoreError:
            return None
        selected = next((item for item in collection.profiles if item.id == profile_id), None)
        return None if selected is None else make_provider(selected)

    agent = AgentService(loop, sessions, settings.agent.system_prompt, memory=memory, profile_service=profile, compressor=compressor, knowledge=None, vision_enabled=settings.llm.supports_vision, model_profile_resolver=resolve_model_profile)
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
    delegation = DelegationService(subagent, DelegationRepository(settings.sessions.directory.parent / "subagent" / "delegation.sqlite3"), settings.subagent.max_parallel_tasks, sessions=sessions)
    subagent.delegation = delegation
    agent.delegation_service = delegation
    resource_closers.append(delegation.close)
    registry.register(build_delegate_task_tool(delegation))
    registry.register(build_delegate_tasks_tool(delegation))
    registry.register(build_delegate_workflow_tool(delegation))
    registry.register(build_request_subagent_collaboration_tool())
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
        summarizer=PageSummarizer(provider, max_summary_chars=800, input_truncate_chars=6000),
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
    registry.register(build_collect_interview_knowledge_tool(web_search_client, page_fetcher))
    runtime_config_path = settings.knowledge.files_directory.parent / "runtime.json"
    runtime_defaults = _rag_runtime_defaults(settings)
    runtime_models = load_runtime_config(runtime_config_path, runtime_defaults)
    rag_embedder = OllamaEmbedder(
        model=str(runtime_models["embedding_model"]),
        base_url=str(runtime_models["embedding_base_url"]),
        timeout=settings.knowledge.embedding_timeout_seconds,
    ) if runtime_models["embedding_enabled"] else None
    graph_extractor = OllamaGraphExtractor(
        model=runtime_models["graph_model"],
        base_url=runtime_models["graph_base_url"],
        timeout=settings.knowledge.graph_extraction_timeout_seconds,
    ) if runtime_models["graph_enabled"] else None
    semantic_splitter = LocalSemanticSplitter(OllamaEmbedder(
        model=runtime_models["semantic_split_model"],
        base_url=runtime_models["semantic_split_base_url"],
        timeout=settings.knowledge.semantic_split_timeout_seconds,
    ), owns_embedder=True
    ) if runtime_models["semantic_split_enabled"] else None
    image_parser = OllamaImageDescriber(
        model=runtime_models["image_model"],
        base_url=runtime_models["image_base_url"],
        timeout=settings.knowledge.image_parsing_timeout_seconds,
    ) if runtime_models["image_enabled"] else None
    reranker = build_reranker(
        runtime_models["reranker_provider"] if runtime_models["reranker_enabled"] else "none",
        model=runtime_models["reranker_model"],
        base_url=runtime_models["reranker_base_url"],
        api_key=settings.knowledge.reranker_api_key,
        timeout=settings.knowledge.reranker_timeout_seconds,
    )
    knowledge = RagKnowledgeService(
        SqliteKnowledgeRepository(settings.knowledge.database_file), embedder=rag_embedder,
        files_directory=settings.knowledge.files_directory, chunk_target_chars=settings.knowledge.chunk_target_chars,
        chunk_overlap_chars=settings.knowledge.chunk_overlap_chars, embedding_batch_size=settings.knowledge.embedding_batch_size,
        retrieval_limit=settings.knowledge.retrieval_limit, max_context_chars=settings.knowledge.max_context_chars,
        minimum_relevance_score=settings.knowledge.minimum_relevance_score, max_file_bytes=settings.knowledge.max_file_bytes,
        max_total_bytes=settings.knowledge.max_total_bytes, max_document_count=settings.knowledge.max_document_count,
        allowed_extensions=settings.knowledge.allowed_upload_extensions,
        graph_extractor=graph_extractor,
        semantic_splitter=semantic_splitter,
        image_parser=image_parser,
        reranker=reranker, reranker_candidates=settings.knowledge.reranker_candidates,
        rrf_k=settings.knowledge.rrf_k,
        retrieval_candidate_multiplier=settings.knowledge.retrieval_candidate_multiplier,
        parent_chunk_target_chars=(settings.knowledge.parent_chunk_target_chars if settings.knowledge.chunk_strategy == "parent_child" else None),
        child_chunk_target_chars=(settings.knowledge.child_chunk_target_chars if settings.knowledge.chunk_strategy == "parent_child" else None),
        child_chunk_overlap_chars=(settings.knowledge.child_chunk_overlap_chars if settings.knowledge.chunk_strategy == "parent_child" else None),
        model_config=runtime_models, runtime_config_path=runtime_config_path,
        reranker_api_key=settings.knowledge.reranker_api_key,
        embedding_timeout_seconds=settings.knowledge.embedding_timeout_seconds,
        graph_timeout_seconds=settings.knowledge.graph_extraction_timeout_seconds,
        semantic_split_timeout_seconds=settings.knowledge.semantic_split_timeout_seconds,
        image_timeout_seconds=settings.knowledge.image_parsing_timeout_seconds,
        reranker_timeout_seconds=settings.knowledge.reranker_timeout_seconds,
    )
    resource_closers.append(knowledge.close)
    registry.register(build_add_knowledge_tool(knowledge))
    knowledge_orchestrator = KnowledgeOrchestrator(
        rag=knowledge,
        memory=memory,
        session_search=session_search,
        sessions=sessions,
        max_context_chars=settings.knowledge.max_context_chars,
    )
    agent.capability_resolver = CapabilityResolver(registry, {
        "safe": ("current_time", "list_directory", "read_file", "recall", "read_attachment", "request_subagent_collaboration"),
        "research": ("web_search", "fetch_page", "collect_interview_knowledge"),
        "coding": ("write_file", "replace_in_file", "run_command"),
        "knowledge": ("search_knowledge", "add_knowledge"),
        "skills": ("use_skill", "save_skill", "remember"),
        "delegation": ("delegate_task", "delegate_tasks", "delegate_workflow"),
    })
    agent.knowledge = knowledge
    agent.knowledge_orchestrator = knowledge_orchestrator
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
    napcat = NapCatLauncher(settings.gateway.directory / "napcat.json")
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
    return ApplicationServices(agent, sessions, reports, attachments, skills, hot_radar, automation, notifications, task_center, task_queue, memory, session_search, subagent, profile, knowledge, curator, mcp, mcp_tools, gateway, qq_adapter, napcat, wecom_adapter, settings, settings_profiles, chat_attachments, tuple(resource_closers))
