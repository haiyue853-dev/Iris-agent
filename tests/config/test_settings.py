from pathlib import Path

import pytest

from iris_agent.config.settings import load_settings
from iris_agent.core.errors import ConfigurationError


def test_default_knowledge_settings_enable_local_rag_paths(tmp_path):
    knowledge = load_settings(tmp_path / "missing.yaml").knowledge

    assert knowledge.database_file == Path("data/knowledge/knowledge.db")
    assert knowledge.files_directory == Path("data/knowledge/files")
    assert knowledge.chunk_target_chars == 800
    assert knowledge.chunk_overlap_chars == 120
    assert knowledge.embedding_model == "bge-m3"
    assert knowledge.allowed_upload_extensions == (".pdf", ".docx", ".xlsx", ".xls", ".md", ".txt")


def test_knowledge_upload_extensions_are_normalized_to_a_nonempty_tuple(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("knowledge:\n  allowed_upload_extensions: [PDF, .DOCX, txt, .pdf]\n", encoding="utf-8")

    assert load_settings(path).knowledge.allowed_upload_extensions == (".pdf", ".docx", ".txt")


@pytest.mark.parametrize("value", ["[]", "[' ']", "true"])
def test_knowledge_upload_extensions_must_not_be_empty_or_invalid(tmp_path, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"knowledge:\n  allowed_upload_extensions: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="allowed_upload_extensions"):
        load_settings(path)


@pytest.mark.parametrize("value", ["800.5", "true"])
def test_knowledge_integer_settings_reject_floats_and_booleans(tmp_path, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"knowledge:\n  chunk_target_chars: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="chunk_target_chars"):
        load_settings(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_file_bytes", 0),
        ("max_total_bytes", 0),
        ("max_document_count", 0),
        ("chunk_target_chars", 0),
        ("embedding_batch_size", 0),
        ("retrieval_limit", 0),
        ("max_context_chars", 0),
        ("minimum_relevance_score", -0.01),
        ("minimum_relevance_score", 1.01),
    ],
)
def test_knowledge_settings_reject_invalid_ranges(tmp_path, field, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"knowledge:\n  {field}: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match=field):
        load_settings(path)


def test_knowledge_settings_reject_overlap_at_or_above_target(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("knowledge:\n  chunk_target_chars: 120\n  chunk_overlap_chars: 120\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="chunk_overlap_chars"):
        load_settings(path)


def test_environment_overrides_yaml(tmp_path, monkeypatch):
    path = tmp_path / "agent.yaml"
    path.write_text("llm:\n  model: yaml-model\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    assert load_settings(path).llm.model == "env-model"


def test_tavily_key_comes_only_from_environment(tmp_path, monkeypatch):
    path = tmp_path / "agent.yaml"
    path.write_text("web_search:\n  tavily_api_key: yaml-secret\n", encoding="utf-8")
    monkeypatch.setenv("TAVILY_API_KEY", "env-secret")

    assert load_settings(path).web_search.tavily_api_key == "env-secret"


def test_tavily_key_is_excluded_from_settings_repr(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "super-secret-tavily-key")

    settings = load_settings(tmp_path / "missing.yaml")

    assert "super-secret-tavily-key" not in repr(settings.web_search)
    assert "super-secret-tavily-key" not in repr(settings)


def test_tavily_yaml_key_is_ignored_when_environment_missing(tmp_path, monkeypatch):
    path = tmp_path / "agent.yaml"
    path.write_text("web_search:\n  tavily_api_key: yaml-secret\n", encoding="utf-8")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    assert load_settings(path).web_search.tavily_api_key == ""


def test_tavily_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    web_search = load_settings(tmp_path / "missing.yaml").web_search

    assert web_search.enable_tavily is True
    assert web_search.tavily_api_key == ""
    assert web_search.default_search_depth == "basic"
    assert web_search.max_download_bytes == 2_000_000
    assert web_search.timeout_seconds == 6
    assert web_search.max_retries == 1


def test_tavily_non_secret_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "web_search:\n  enable_tavily: false\n  default_search_depth: advanced\n",
        encoding="utf-8",
    )

    web_search = load_settings(path).web_search

    assert web_search.enable_tavily is False
    assert web_search.default_search_depth == "advanced"


def test_tavily_search_depth_must_be_supported(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("web_search:\n  default_search_depth: exhaustive\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_settings(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_results", 0),
        ("max_results", 21),
        ("timeout_seconds", 0),
        ("max_snippet_chars", 0),
        ("max_page_chars", 0),
        ("min_text_chars", 0),
        ("max_retries", 0),
    ],
)
def test_web_search_numeric_settings_reject_invalid_ranges(tmp_path, field, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  {field}: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_settings(path)


@pytest.mark.parametrize("max_results", [1, 20])
def test_web_search_max_results_accepts_boundaries(tmp_path, max_results):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  max_results: {max_results}\n", encoding="utf-8")

    assert load_settings(path).web_search.max_results == max_results


@pytest.mark.parametrize("max_download_bytes", [1, 20_000_000])
def test_web_search_max_download_bytes_accepts_boundaries(tmp_path, max_download_bytes):
    path = tmp_path / "agent.yaml"
    path.write_text(
        f"web_search:\n  max_download_bytes: {max_download_bytes}\n",
        encoding="utf-8",
    )

    assert load_settings(path).web_search.max_download_bytes == max_download_bytes


@pytest.mark.parametrize("value", [0, -1, 20_000_001, "not-a-number"])
def test_web_search_max_download_bytes_rejects_invalid_values(tmp_path, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  max_download_bytes: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="max_download_bytes"):
        load_settings(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_results", "not-a-number"),
        ("max_snippet_chars", "not-a-number"),
        ("max_page_chars", "not-a-number"),
        ("min_text_chars", "not-a-number"),
        ("max_retries", "not-a-number"),
        ("timeout_seconds", "not-a-number"),
    ],
)
def test_web_search_numeric_settings_wrap_conversion_errors(tmp_path, field, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  {field}: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match=field):
        load_settings(path)


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_web_search_timeout_rejects_non_finite_values(tmp_path, value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  timeout_seconds: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="timeout_seconds"):
        load_settings(path)


@pytest.mark.parametrize(
    "field",
    ["max_results", "max_snippet_chars", "max_page_chars", "min_text_chars", "max_retries"],
)
def test_web_search_integer_settings_reject_negative_values(tmp_path, field):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  {field}: -1\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_settings(path)


@pytest.mark.parametrize(
    "field",
    [
        "max_results",
        "max_snippet_chars",
        "max_page_chars",
        "max_download_bytes",
        "min_text_chars",
        "max_retries",
    ],
)
@pytest.mark.parametrize("yaml_value", ["true", "1.0", "'1.5'", "'1e2'"])
def test_web_search_integer_settings_reject_non_integer_types(tmp_path, field, yaml_value):
    path = tmp_path / "agent.yaml"
    path.write_text(f"web_search:\n  {field}: {yaml_value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match=field):
        load_settings(path)


def test_web_search_integer_settings_accept_decimal_strings(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("web_search:\n  max_results: '20'\n", encoding="utf-8")

    assert load_settings(path).web_search.max_results == 20


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


def test_chat_attachment_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")
    assert settings.attachments.directory == Path("data/chat_attachments")
    assert settings.attachments.max_file_bytes == 10_000_000
    assert settings.attachments.max_total_bytes == 50_000_000
    assert settings.attachments.max_count == 10
    assert settings.attachments.max_text_chars == 50_000
    assert settings.attachments.temporary_ttl_seconds == 86_400


def test_chat_attachment_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("attachments:\n  directory: custom/chat\n  max_file_bytes: 123\n  max_total_bytes: 456\n  max_count: 3\n  max_text_chars: 789\n  temporary_ttl_seconds: 99\n", encoding="utf-8")
    settings = load_settings(path).attachments
    assert settings.directory == Path("custom/chat")
    assert settings.max_file_bytes == 123
    assert settings.max_total_bytes == 456
    assert settings.max_count == 3
    assert settings.max_text_chars == 789
    assert settings.temporary_ttl_seconds == 99


@pytest.mark.parametrize("field", ["max_file_bytes", "max_total_bytes", "max_count", "max_text_chars", "temporary_ttl_seconds"])
def test_chat_attachment_numeric_settings_must_be_positive(tmp_path, field):
    path = tmp_path / "agent.yaml"
    path.write_text(f"attachments:\n  {field}: 0\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(path)


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


def test_gateway_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.gateway.enabled is False
    assert settings.gateway.directory == Path("data/gateway")
    assert settings.gateway.qq.enabled is False
    assert settings.gateway.qq.path == "/gateway/qq/ws"
    assert settings.gateway.qq.respond_groups is False
    assert settings.gateway.qq.allowed_users == []
    assert settings.gateway.qq.allow_all is False
    assert settings.gateway.wecom.enabled is False
    assert settings.gateway.push.enabled is False
    assert settings.gateway.push.qq_target == ""


def test_gateway_settings_load_from_yaml(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        "gateway:\n"
        "  enabled: true\n"
        "  qq:\n"
        "    enabled: true\n"
        "    respond_groups: true\n"
        "    allowed_users: '12345, 67890'\n"
        "    allow_all: true\n"
        "  wecom:\n"
        "    enabled: true\n"
        "    corp_id: corp123\n"
        "    agent_id: 1000002\n"
        "  push:\n"
        "    enabled: true\n"
        "    qq_target: '123456789'\n",
        encoding="utf-8",
    )

    gateway = load_settings(path).gateway

    assert gateway.enabled is True
    assert gateway.qq.enabled is True
    assert gateway.qq.respond_groups is True
    assert gateway.qq.allowed_users == ["12345", "67890"]
    assert gateway.qq.allow_all is True
    assert gateway.wecom.enabled is True
    assert gateway.wecom.corp_id == "corp123"
    assert gateway.wecom.agent_id == 1000002
    assert gateway.push.enabled is True
    assert gateway.push.qq_target == "123456789"
