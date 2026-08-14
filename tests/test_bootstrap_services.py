from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationService
from iris_agent.bootstrap import ApplicationServices, build_application
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.mcp_center.service import McpServer, McpCenterService


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "agent.yaml"
    sessions_directory = (tmp_path / "sessions").as_posix()
    reports_directory = (tmp_path / "reports").as_posix()
    attachments_directory = (tmp_path / "attachments").as_posix()
    skills_directory = (tmp_path / "skills").as_posix()
    hot_radar_directory = (tmp_path / "hot_radar").as_posix()
    automation_directory = (tmp_path / "automation").as_posix()
    workspace_directory = (tmp_path / "workspace").as_posix()
    config.write_text(
        "llm:\n"
        "  model: test-model\n"
        "sessions:\n"
        f"  directory: {sessions_directory}\n"
        "reports:\n"
        f"  directory: {reports_directory}\n"
        f"  attachments_directory: {attachments_directory}\n"
        "skills:\n"
        f"  directory: {skills_directory}\n"
        "hot_radar:\n"
        f"  directory: {hot_radar_directory}\n"
        "automation:\n"
        f"  directory: {automation_directory}\n"
        "tools:\n"
        f"  workspace_root: {workspace_directory}\n",
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
    monkeypatch.setattr(McpCenterService, "enabled_tools", lambda _, *args, **kwargs: ((server, {
        "name": "get_page", "description": "Read page", "inputSchema": {"type": "object", "properties": {}},
    }),))

    application = build_application(config)

    assert "mcp__browser__get_page" in [item["function"]["name"] for item in application.agent.loop.tools.schemas()]


def test_build_application_registers_builtin_interview_mcp_tools(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    application = build_application(config)
    names = [item["function"]["name"] for item in application.agent.loop.tools.schemas()]
    assert "mcp__builtin-interview-web__search_interview_sources" in names
    assert application.agent.loop.tools.requires_approval("mcp__builtin-interview-web__save_interview_qa")


def test_server_entrypoint_loads_without_document_service(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import importlib
    from fastapi.testclient import TestClient
    server = importlib.import_module("server")
    assert TestClient(server.app).post("/api/hot-radar/scan").status_code == 200
    assert TestClient(server.app).get("/api/automation/tasks").status_code == 200
