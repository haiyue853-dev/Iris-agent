from pathlib import Path

import pytest

from iris_agent.config.settings import load_settings
from iris_agent.core.errors import ConfigurationError


def test_environment_overrides_yaml(tmp_path, monkeypatch):
    path = tmp_path / "agent.yaml"
    path.write_text("llm:\n  model: yaml-model\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    assert load_settings(path).llm.model == "env-model"


def test_explicit_override_wins_over_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "env-model")
    assert load_settings(tmp_path / "missing.yaml", model="explicit").llm.model == "explicit"


def test_report_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.reports.directory == Path("data/reports")
    assert settings.reports.attachments_directory == Path("data/report_attachments")
    assert settings.reports.max_input_chars == 50_000
    assert settings.reports.max_revision_chars == 2_000
    assert settings.reports.max_versions == 20
    assert settings.reports.max_attachment_bytes == 10_000_000
    assert settings.reports.max_attachment_total_bytes == 50_000_000
    assert settings.reports.max_attachment_count == 10
    assert settings.reports.max_attachment_text_chars == 20_000


def test_report_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "reports:\n"
        "  directory: custom/reports\n"
        "  max_input_chars: 1234\n"
        "  max_revision_chars: 321\n"
        "  max_versions: 7\n"
        "  attachments_directory: custom/attachments\n"
        "  max_attachment_bytes: 123\n"
        "  max_attachment_total_bytes: 456\n"
        "  max_attachment_count: 3\n"
        "  max_attachment_text_chars: 789\n",
        encoding="utf-8",
    )

    reports = load_settings(path).reports

    assert reports.directory == Path("custom/reports")
    assert reports.max_input_chars == 1234
    assert reports.max_revision_chars == 321
    assert reports.max_versions == 7
    assert reports.attachments_directory == Path("custom/attachments")
    assert reports.max_attachment_bytes == 123
    assert reports.max_attachment_total_bytes == 456
    assert reports.max_attachment_count == 3
    assert reports.max_attachment_text_chars == 789


@pytest.mark.parametrize(
    "field",
    [
        "max_input_chars",
        "max_revision_chars",
        "max_versions",
        "max_attachment_bytes",
        "max_attachment_total_bytes",
        "max_attachment_count",
        "max_attachment_text_chars",
    ],
)
def test_report_numeric_settings_must_be_positive(tmp_path, field):
    path = tmp_path / "agent.yaml"
    path.write_text(f"reports:\n  {field}: 0\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_settings(path)


def test_skill_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.skills.directory == Path("data/skills")
    assert settings.skills.settings_file == Path("data/skills/settings.json")


def test_skill_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "skills:\n  directory: custom/skills\n  settings_file: custom/skills/state.json\n",
        encoding="utf-8",
    )

    skills = load_settings(path).skills

    assert skills.directory == Path("custom/skills")
    assert skills.settings_file == Path("custom/skills/state.json")


def test_document_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.documents.directory == Path("data/documents")
    assert settings.documents.max_file_bytes == 10_000_000
    assert settings.documents.max_total_bytes == 50_000_000
    assert settings.documents.max_count == 50
    assert settings.documents.max_text_chars == 50_000


def test_document_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "documents:\n"
        "  directory: custom/docs\n"
        "  max_file_bytes: 123\n"
        "  max_total_bytes: 456\n"
        "  max_count: 5\n"
        "  max_text_chars: 789\n",
        encoding="utf-8",
    )

    docs = load_settings(path).documents

    assert docs.directory == Path("custom/docs")
    assert docs.max_file_bytes == 123
    assert docs.max_total_bytes == 456
    assert docs.max_count == 5
    assert docs.max_text_chars == 789


def test_hot_radar_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.hot_radar.directory == Path("data/hot_radar")
    assert settings.hot_radar.poll_interval_seconds == 60
    assert settings.hot_radar.timezone == "Asia/Shanghai"


def test_hot_radar_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "hot_radar:\n"
        "  directory: custom/radar\n"
        "  poll_interval_seconds: 5\n"
        "  timezone: UTC\n",
        encoding="utf-8",
    )

    radar = load_settings(path).hot_radar

    assert radar.directory == Path("custom/radar")
    assert radar.poll_interval_seconds == 5
    assert radar.timezone == "UTC"
