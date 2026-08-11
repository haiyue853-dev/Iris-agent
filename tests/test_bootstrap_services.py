from pathlib import Path

from iris_agent.api.app import create_app
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
        "documents:\n"
        f"  directory: {str(tmp_path / 'documents').replace('\\', '/')}\n"
        "hot_radar:\n"
        f"  directory: {str(tmp_path / 'hot_radar').replace('\\', '/')}\n"
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


def test_build_application_exposes_document_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.documents is not None
    assert application.documents.root == tmp_path / "documents"
    assert (tmp_path / "documents").is_dir()


def test_build_application_exposes_hot_radar_service(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert application.hot_radar is not None
    assert application.hot_radar.root == tmp_path / "hot_radar"
    assert (tmp_path / "hot_radar").is_dir()


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
    monkeypatch.setattr(McpCenterService, "enabled_tools", lambda _: ((server, {
        "name": "get_page", "description": "Read page", "inputSchema": {"type": "object", "properties": {}},
    }),))

    application = build_application(config)

    assert "mcp__browser__get_page" in [item["function"]["name"] for item in application.agent.loop.tools.schemas()]
