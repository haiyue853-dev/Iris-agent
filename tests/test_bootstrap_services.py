from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.bootstrap import ApplicationServices, build_application
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
