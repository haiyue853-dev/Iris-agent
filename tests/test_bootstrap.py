from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.bootstrap import ApplicationServices, build_application
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.service import DailyReportService


def test_build_application_exposes_daily_report_service(tmp_path, monkeypatch):
    config = tmp_path / "agent.yaml"
    sessions_directory = (tmp_path / "sessions").as_posix()
    reports_directory = (tmp_path / "reports").as_posix()
    attachments_directory = (tmp_path / "attachments").as_posix()
    workspace_directory = (tmp_path / "workspace").as_posix()
    config.write_text(
        "llm:\n"
        "  model: test-model\n"
        "sessions:\n"
        f"  directory: {sessions_directory}\n"
        "reports:\n"
        f"  directory: {reports_directory}\n"
        f"  attachments_directory: {attachments_directory}\n"
        "tools:\n"
        f"  workspace_root: {workspace_directory}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application = build_application(config)

    assert isinstance(application, ApplicationServices)
    assert isinstance(application.reports, DailyReportService)
    assert isinstance(application.attachments, AttachmentRepository)
    assert application.settings.reports.directory == Path(tmp_path / "reports")
    assert application.reports.sessions is application.sessions
    assert application.attachments.root == tmp_path / "attachments"
    assert create_app(application.agent, application.sessions, application.reports).title == "Iris Agent API"

