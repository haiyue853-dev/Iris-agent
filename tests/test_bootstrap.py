from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.bootstrap import ApplicationServices, build_application
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.service import DailyReportService


def test_build_application_exposes_daily_report_service(tmp_path, monkeypatch):
    config = tmp_path / "agent.yaml"
    config.write_text(
        "llm:\n"
        "  model: test-model\n"
        "sessions:\n"
        f"  directory: {str(tmp_path / 'sessions').replace('\\', '/')}\n"
        "reports:\n"
        f"  directory: {str(tmp_path / 'reports').replace('\\', '/')}\n"
        f"  attachments_directory: {str(tmp_path / 'attachments').replace('\\', '/')}\n"
        "tools:\n"
        f"  workspace_root: {str(tmp_path / 'workspace').replace('\\', '/')}\n",
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

