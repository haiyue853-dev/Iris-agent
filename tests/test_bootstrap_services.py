from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.bootstrap import ApplicationServices, build_application
from iris_agent.knowledge.retriever import HybridRetriever, KeywordRetriever
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.mcp_center.service import McpServer, McpCenterService
from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource, TavilySearchSource


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "agent.yaml"
    config.write_text(
        "llm:\n"
        "  model: test-model\n"
        "sessions:\n"
        f"  directory: {str(tmp_path / 'sessions').replace('\\', '/')}\n"
        "reports:\n"
        f"  directory: {str(tmp_path / 'reports').replace('\\', '/')}\n"
        f"  attachments_directory: {str(tmp_path / 'attachments').replace('\\', '/')}\n"
        "skills:\n"
        f"  directory: {str(tmp_path / 'skills').replace('\\', '/')}\n"
        "hot_radar:\n"
        f"  directory: {str(tmp_path / 'hot_radar').replace('\\', '/')}\n"
        "automation:\n"
        f"  directory: {str(tmp_path / 'automation').replace('\\', '/')}\n"
        "tools:\n"
        f"  workspace_root: {str(tmp_path / 'workspace').replace('\\', '/')}\n",
        encoding="utf-8",
    )
    return config


def test_build_application_exposes_skill_center_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.skills is not None
    # catalog 指向包内 bundled 目录；状态文件目录为配置的数据目录
    assert application.skills.catalog_root.is_dir()
    assert application.skills.settings_file == tmp_path / "skills" / "settings.json"
    assert (tmp_path / "skills").is_dir()


def test_build_application_no_longer_exposes_document_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert not hasattr(application, "documents")
    assert not (tmp_path / "documents").exists()


def test_build_application_exposes_hot_radar_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.hot_radar is not None
    assert application.hot_radar.root == tmp_path / "hot_radar"
    assert (tmp_path / "hot_radar").is_dir()


def test_build_application_exposes_automation_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application.automation, AutomationService)
    assert application.automation.root == tmp_path / "automation"


def test_build_application_exposes_task_queue_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.task_queue.task_center is application.task_center
    assert application.task_queue.agent_service is application.agent
    assert application.task_queue.repository.root == Path("data/task_queue")


def test_build_application_exposes_memory_service_and_remember_tool(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.memory is not None
    assert application.agent.memory is application.memory
    assert application.memory.repository.root == Path("data/memory")
    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "remember" in tool_names


def test_build_application_exposes_session_search_and_recall_tool(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.session_search is not None
    assert application.session_search.sessions is application.sessions
    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "recall" in tool_names


def test_build_application_registers_skill_tools(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "use_skill" in tool_names
    assert "save_skill" in tool_names


def test_build_application_exposes_subagent_runner_and_delegate_tool(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.subagent is not None
    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "delegate_task" in tool_names
    assert "delegate_tasks" in tool_names
    # 子代理默认工具集不含写工具与 delegate_task/delegate_tasks（防递归）
    sub_tools = application.subagent.tool_subset(application.subagent.default_allowed_tools)
    sub_tool_names = {schema["function"]["name"] for schema in sub_tools.schemas()}
    assert "delegate_task" not in sub_tool_names
    assert "delegate_tasks" not in sub_tool_names
    assert "remember" not in sub_tool_names
    assert "save_skill" not in sub_tool_names


def test_build_application_exposes_profile_service_and_wires_into_agent(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.profile is not None
    assert application.agent.profile_service is application.profile
    assert application.profile.repository.root == Path("data/profile")


def test_build_application_wires_compressor_into_agent(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.agent.compressor is not None
    assert application.agent.compressor.trigger_chars == 12000
    assert application.agent.compressor.keep_recent == 10


def test_build_application_registers_web_search_tools(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "web_search" in tool_names
    assert "fetch_page" in tool_names


def test_build_application_exposes_knowledge_service_and_tools(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.knowledge is not None
    assert application.knowledge.repository.root == Path("data/knowledge")
    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "add_knowledge" in tool_names
    assert "search_knowledge" in tool_names


def test_build_application_knowledge_defaults_to_keyword(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application.knowledge.retriever, KeywordRetriever)
    assert application.knowledge.fallback_retriever is None


def test_build_application_knowledge_hybrid_has_keyword_fallback(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "knowledge:\n  retriever: hybrid\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application.knowledge.retriever, HybridRetriever)
    assert isinstance(application.knowledge.fallback_retriever, KeywordRetriever)


def test_build_application_exposes_curator_service(tmp_path, monkeypatch):
    from iris_agent.curator.service import CuratorService

    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application.curator, CuratorService)
    assert application.curator.memory is application.memory
    assert application.curator.profile is application.profile
    assert application.curator.repository.root == Path("data/curator")
    assert application.curator.enable_llm is True
    assert application.curator.engine is not None


def test_build_application_default_search_sources_are_bing_only(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.settings.web_search.enable_duckduckgo is False
    assert application.settings.web_search.max_retries == 1
    assert application.settings.web_search.timeout_seconds == 6
    assert application.settings.web_search.enable_browser_fallback is False
    assert application.settings.web_search.browser_channel == "msedge"


def _capture_web_search_client(monkeypatch):
    captured = {}

    class FakeWebSearchClient:
        last_error = None

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def search(self, query, limit=None, options=None):
            return []

    monkeypatch.setattr("iris_agent.bootstrap.WebSearchClient", FakeWebSearchClient)
    return captured


def test_build_application_does_not_add_tavily_without_key(tmp_path, monkeypatch):
    captured = _capture_web_search_client(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    build_application(_write_config(tmp_path))

    assert [type(source) for source in captured["sources"]] == [BingSearchSource]


def test_build_application_adds_tavily_first_when_key_present(tmp_path, monkeypatch):
    captured = _capture_web_search_client(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "web_search:\n  enable_duckduckgo: true\n",
        encoding="utf-8",
    )

    build_application(config)

    assert [type(source) for source in captured["sources"]] == [
        TavilySearchSource,
        BingSearchSource,
        DuckDuckGoSearchSource,
    ]


def test_build_application_respects_disabled_tavily(tmp_path, monkeypatch):
    captured = _capture_web_search_client(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "web_search:\n  enable_tavily: false\n",
        encoding="utf-8",
    )

    build_application(config)

    assert [type(source) for source in captured["sources"]] == [BingSearchSource]


def test_build_application_passes_search_retries(tmp_path, monkeypatch):
    captured = _capture_web_search_client(monkeypatch)
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "web_search:\n  max_retries: 7\n",
        encoding="utf-8",
    )

    build_application(config)

    assert captured["max_retries"] == 7


def test_build_application_passes_configured_default_search_depth(tmp_path, monkeypatch):
    captured = {}

    def fake_build_web_search_tool(client, default_search_depth="basic"):
        captured["default_search_depth"] = default_search_depth
        from iris_agent.tools.builtin.web_tools import build_web_search_tool
        return build_web_search_tool(client, default_search_depth=default_search_depth)

    monkeypatch.setattr("iris_agent.bootstrap.build_web_search_tool", fake_build_web_search_tool)
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "web_search:\n  default_search_depth: advanced\n",
        encoding="utf-8",
    )

    build_application(config)

    assert captured["default_search_depth"] == "advanced"


def test_build_application_passes_max_download_bytes_to_page_fetcher(tmp_path, monkeypatch):
    captured = {}

    class FakePageFetcher:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def fetch(self, url):
            return ""

        def close(self):
            pass

    monkeypatch.setattr("iris_agent.bootstrap.PageFetcher", FakePageFetcher)
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "web_search:\n  max_download_bytes: 123456\n",
        encoding="utf-8",
    )

    build_application(config)

    assert captured["max_download_bytes"] == 123456


def test_build_application_passes_max_download_bytes_to_browser_fetcher(tmp_path, monkeypatch):
    captured = {}

    class FakeBrowserFetcher:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def fetch(self, url):
            return ""

    monkeypatch.setattr("iris_agent.bootstrap.BrowserFetcher", FakeBrowserFetcher)
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "web_search:\n  enable_browser_fallback: true\n  max_download_bytes: 654321\n  timeout_seconds: 7.5\n",
        encoding="utf-8",
    )

    build_application(config)

    assert captured["max_download_bytes"] == 654321
    assert captured["timeout"] == 7.5


def test_application_close_releases_tavily_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr("iris_agent.bootstrap.TavilySearchSource.close", lambda self: calls.append(self))

    application = build_application(_write_config(tmp_path))
    application.close()
    application.close()

    assert len(calls) == 1


def test_application_close_runs_all_closers_in_reverse_and_reraises_first_error():
    calls = []

    def closer(name, error=None):
        def run():
            calls.append(name)
            if error is not None:
                raise error
        return run

    application = object.__new__(ApplicationServices)
    object.__setattr__(
        application,
        "_closers",
        (closer("first", ValueError("first error")), closer("second"), closer("third", RuntimeError("third error"))),
    )
    object.__setattr__(application, "_closed", False)

    import pytest
    with pytest.raises(RuntimeError, match="third error"):
        application.close()
    application.close()

    assert calls == ["third", "second", "first"]


def test_multiple_applications_own_independent_tavily_resources(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr("iris_agent.bootstrap.TavilySearchSource.close", lambda self: calls.append(self))

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = build_application(_write_config(first_root))
    second = build_application(_write_config(second_root))
    first.close()
    second.close()

    assert len(calls) == 2
    assert calls[0] is not calls[1]


def test_build_failure_releases_created_tavily(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr("iris_agent.bootstrap.TavilySearchSource.close", lambda self: calls.append(self))

    def fail_repository(*args, **kwargs):
        raise RuntimeError("build failed")

    monkeypatch.setattr("iris_agent.bootstrap.KnowledgeRepository", fail_repository)

    import pytest
    with pytest.raises(RuntimeError, match="build failed"):
        build_application(_write_config(tmp_path))

    assert len(calls) == 1


def test_application_close_releases_owned_html_sources_and_page_fetcher(tmp_path, monkeypatch):
    calls = []
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("iris_agent.bootstrap.BingSearchSource.close", lambda self: calls.append("bing"))
    monkeypatch.setattr("iris_agent.bootstrap.DuckDuckGoSearchSource.close", lambda self: calls.append("ddg"))
    monkeypatch.setattr("iris_agent.bootstrap.PageFetcher.close", lambda self: calls.append("page"))
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "web_search:\n  enable_duckduckgo: true\n",
        encoding="utf-8",
    )

    application = build_application(config)
    application.close()

    assert calls == ["page", "ddg", "bing"]


def test_multiple_applications_release_their_own_html_and_page_resources(tmp_path, monkeypatch):
    calls = []
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("iris_agent.bootstrap.BingSearchSource.close", lambda self: calls.append(("bing", self)))
    monkeypatch.setattr("iris_agent.bootstrap.PageFetcher.close", lambda self: calls.append(("page", self)))
    first_root = tmp_path / "first-extra"
    second_root = tmp_path / "second-extra"
    first_root.mkdir()
    second_root.mkdir()

    first = build_application(_write_config(first_root))
    second = build_application(_write_config(second_root))
    first.close()
    second.close()

    assert [name for name, _ in calls] == ["page", "bing", "page", "bing"]
    assert len({id(resource) for _, resource in calls}) == 4


def test_build_failure_releases_html_sources_and_page_fetcher(tmp_path, monkeypatch):
    calls = []
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("iris_agent.bootstrap.BingSearchSource.close", lambda self: calls.append("bing"))
    monkeypatch.setattr("iris_agent.bootstrap.PageFetcher.close", lambda self: calls.append("page"))
    monkeypatch.setattr(
        "iris_agent.bootstrap.KnowledgeRepository",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("build failed")),
    )

    import pytest
    with pytest.raises(RuntimeError, match="build failed"):
        build_application(_write_config(tmp_path))

    assert calls == ["page", "bing"]


def test_build_application_preserves_existing_services(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application, ApplicationServices)
    assert isinstance(application.reports, DailyReportService)
    assert isinstance(application.attachments, AttachmentRepository)
    assert application.settings.reports.directory == Path(tmp_path / "reports")
    assert create_app(application.agent, application.sessions, application.reports).title == "Iris Agent API"


def test_build_application_registers_enabled_mcp_tools(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    server = McpServer("browser", "Browser", "node", (), ("get_page",), True)
    monkeypatch.setattr(McpCenterService, "enabled_tools", lambda _, **kwargs: ((server, {
        "name": "get_page", "description": "Read page", "inputSchema": {"type": "object", "properties": {}},
    }),))

    application = build_application(config)

    assert "mcp__browser__get_page" in [item["function"]["name"] for item in application.agent.loop.tools.schemas()]


def test_server_entrypoint_loads_without_document_service(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import importlib
    from fastapi.testclient import TestClient
    server = importlib.import_module("server")
    assert TestClient(server.app).post("/api/hot-radar/scan").status_code == 200
    assert TestClient(server.app).get("/api/automation/tasks").status_code == 200


def test_server_lifecycle_starts_and_stops_task_queue(monkeypatch):
    import importlib
    from fastapi.testclient import TestClient

    server = importlib.import_module("server")
    calls: list[str] = []
    monkeypatch.setattr(server.application.task_queue, "start", lambda: calls.append("start"))
    monkeypatch.setattr(server.application.task_queue, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(type(server.application), "close", lambda self: calls.append("close"))

    with TestClient(server.app):
        assert calls == ["start"]

    assert calls == ["start", "stop", "close"]


def test_build_application_gateway_disabled_by_default(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.gateway is not None
    assert application.qq_adapter is None
    assert application.wecom_adapter is None


def test_build_application_enables_qq_gateway(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8") + "gateway:\n  qq:\n    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.qq_adapter is not None
    assert application.wecom_adapter is None


def test_build_application_enables_wecom_gateway(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "gateway:\n  wecom:\n    enabled: true\n    corp_id: corp\n    agent_id: 1\n"
        + "    secret: s\n    token: t\n    aes_key: abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.wecom_adapter is not None
    assert application.qq_adapter is None


def test_create_app_registers_gateway_endpoints_when_enabled(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "gateway:\n  qq:\n    enabled: true\n"
        + "  wecom:\n    enabled: true\n    corp_id: corp\n    agent_id: 1\n"
        + "    secret: s\n    token: t\n    aes_key: abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    application = build_application(config)

    app = create_app(
        application.agent,
        application.sessions,
        qq_adapter=application.qq_adapter,
        wecom_adapter=application.wecom_adapter,
    )

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/gateway/qq/ws" in paths
    assert "/gateway/wecom/callback" in paths
