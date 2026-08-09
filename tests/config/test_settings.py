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
