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


def test_automation_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("automation:\n  directory: custom/automation\n", encoding="utf-8")

    assert load_settings(path).automation.directory == Path("custom/automation")


def test_task_queue_settings_default_and_yaml_override(tmp_path):
    default = load_settings(tmp_path / "missing.yaml")
    path = tmp_path / "agent.yaml"
    path.write_text("task_queue:\n  directory: custom/queue\n", encoding="utf-8")

    assert default.task_queue.directory == Path("data/task_queue")
    assert load_settings(path).task_queue.directory == Path("custom/queue")


def test_curator_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.curator.directory == Path("data/curator")
    assert settings.curator.merge_threshold == 0.85
    assert settings.curator.conflict_threshold == 0.45
    assert settings.curator.enable_llm is True
    assert settings.curator.max_pairs_per_run == 200
    assert settings.curator.max_reports == 50


def test_curator_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "curator:\n"
        "  directory: custom/curator\n"
        "  merge_threshold: 0.9\n"
        "  conflict_threshold: 0.5\n"
        "  enable_llm: false\n"
        "  max_pairs_per_run: 10\n"
        "  max_reports: 5\n",
        encoding="utf-8",
    )

    curator = load_settings(path).curator

    assert curator.directory == Path("custom/curator")
    assert curator.merge_threshold == 0.9
    assert curator.conflict_threshold == 0.5
    assert curator.enable_llm is False
    assert curator.max_pairs_per_run == 10
    assert curator.max_reports == 5


def test_subagent_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.subagent.default_max_rounds == 6
    assert settings.subagent.max_parallel_tasks == 5
    assert settings.subagent.allowed_tools == ["current_time", "list_directory", "read_file", "recall", "use_skill"]


def test_subagent_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "subagent:\n  max_goal_chars: 100\n  default_max_rounds: 3\n  max_parallel_tasks: 8\n  allowed_tools: current_time,read_file\n",
        encoding="utf-8",
    )

    subagent = load_settings(path).subagent

    assert subagent.max_goal_chars == 100
    assert subagent.default_max_rounds == 3
    assert subagent.max_parallel_tasks == 8
    assert subagent.allowed_tools == ["current_time", "read_file"]
