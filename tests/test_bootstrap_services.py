from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.bootstrap import ApplicationServices, build_application
from iris_agent.knowledge.retriever import HybridRetriever, KeywordRetriever
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.mcp_center.service import McpServer, McpCenterService


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
    assert application.settings.web_search.max_retries == 2
    assert application.settings.web_search.enable_browser_fallback is False
    assert application.settings.web_search.browser_channel == "msedge"


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

    with TestClient(server.app):
        assert calls == ["start"]

    assert calls == ["start", "stop"]


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
