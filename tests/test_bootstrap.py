from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.bootstrap import ApplicationServices, build_application
import iris_agent.bootstrap as bootstrap
from iris_agent.settings_profiles.service import ProfileService as SettingsProfileService
from iris_agent.providers.switchable import SwitchableProvider
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


def test_build_application_migrates_env_profile_and_uses_it_for_initial_provider(tmp_path, monkeypatch):
    config = tmp_path / "agent.yaml"
    config.write_text("llm:\n  model: fallback\n  temperature: 0.7\n  timeout_seconds: 23\ntools:\n  workspace_root: " + str(tmp_path / "workspace").replace("\\", "/") + "\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-profile\nOPENAI_BASE_URL=https://profile.example/v1\nLLM_MODEL=profile-model\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "PROJECT_ROOT", tmp_path)

    application = build_application(config)

    assert isinstance(application.settings_profiles, SettingsProfileService)
    assert (tmp_path / "data" / "settings_profiles.json").exists()
    handle = application.agent.loop.get_provider()
    assert isinstance(handle, SwitchableProvider)
    provider = handle.current()
    assert provider.model == "profile-model"
    assert provider.temperature == 0.7
    assert str(provider.client.base_url).rstrip("/") == "https://profile.example/v1"


def test_build_application_without_env_exposes_configured_default_profile(tmp_path, monkeypatch):
    config = tmp_path / "agent.yaml"
    config.write_text(
        "llm:\n  model: configured-model\n  base_url: https://configured.example/v1\n  api_key: configured-key\n"
        "tools:\n  workspace_root: " + str(tmp_path / "workspace").replace("\\", "/") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bootstrap, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    application = build_application(config)
    app = create_app(application.agent, application.sessions, settings_profiles=application.settings_profiles)
    response = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app).get("/api/settings/profiles")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["profiles"]) == 1
    assert payload["active_id"] == payload["profiles"][0]["id"]
    assert payload["profiles"][0]["base_url"] == "https://configured.example/v1"
    assert payload["profiles"][0]["model"] == "configured-model"
    provider = application.agent.loop.get_provider().current()
    assert provider.model == "configured-model"
    assert str(provider.client.base_url).rstrip("/") == "https://configured.example/v1"


def test_corrupt_profile_store_keeps_file_and_uses_llm_fallback(tmp_path, monkeypatch, caplog):
    config = tmp_path / "agent.yaml"
    config.write_text("llm:\n  model: fallback-model\n  base_url: https://fallback.example/v1\n  api_key: fallback-key\ntools:\n  workspace_root: " + str(tmp_path / "workspace").replace("\\", "/") + "\n", encoding="utf-8")
    store_path = tmp_path / "data" / "settings_profiles.json"
    store_path.parent.mkdir()
    store_path.write_text("{broken sk-secret", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "PROJECT_ROOT", tmp_path)

    application = build_application(config)

    assert application.agent.loop.get_provider().current().model == "fallback-model"
    assert store_path.read_text(encoding="utf-8") == "{broken sk-secret"
    assert "sk-secret" not in caplog.text
    assert "Settings profile store unavailable; using configured LLM fallback" in caplog.text
    app = create_app(application.agent, application.sessions, settings_profiles=application.settings_profiles)
    response = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app).get("/api/settings/profiles")
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "settings_store_unavailable"


def test_build_application_shares_one_switchable_provider_across_llm_consumers(tmp_path, monkeypatch):
    config = tmp_path / "agent.yaml"
    config.write_text("llm:\n  model: fallback-model\n  base_url: https://fallback.example/v1\ntools:\n  workspace_root: " + str(tmp_path / "workspace").replace("\\", "/") + "\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_BASE_URL=https://profile.example/v1\nLLM_MODEL=model-a\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "PROJECT_ROOT", tmp_path)

    application = build_application(config)
    handle = application.agent.loop.get_provider()

    assert isinstance(handle, SwitchableProvider)
    assert application.reports.provider is handle
    assert application.subagent.provider is handle
    assert application.profile.extractor.provider is handle
    assert application.agent.compressor.provider is handle
    assert application.curator.referee.provider is handle
