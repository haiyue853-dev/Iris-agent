"""Curator 模型测试：建议/报告的校验与序列化往返。"""

from __future__ import annotations

import pytest

from iris_agent.curator.models import CuratorReport, CuratorSuggestion


def _suggestion(**overrides) -> CuratorSuggestion:
    fields = {
        "id": "sug-0123456789ab",
        "kind": "merge",
        "scope": "memory",
        "field": None,
        "targets": ["memory_a", "memory_b"],
        "keep": "memory_a",
        "drop": "memory_b",
        "summary": "记忆重复",
        "reason": "embedding",
        "applied": False,
        "dismissed": False,
    }
    fields.update(overrides)
    return CuratorSuggestion(**fields)


def test_suggestion_new_generates_id():
    suggestion = CuratorSuggestion.new(
        "merge", "memory", ["a", "b"], "a", "b", "重复", "embedding"
    )
    assert suggestion.id.startswith("sug-")
    assert suggestion.applied is False
    assert suggestion.dismissed is False


def test_suggestion_roundtrip():
    suggestion = _suggestion()
    assert CuratorSuggestion.from_dict(suggestion.to_dict()) == suggestion


def test_suggestion_rejects_bad_kind():
    with pytest.raises(ValueError):
        _suggestion(kind="bogus")


def test_suggestion_rejects_bad_scope():
    with pytest.raises(ValueError):
        _suggestion(scope="bogus")


def test_suggestion_profile_requires_field():
    with pytest.raises(ValueError):
        _suggestion(scope="profile", field=None)


def test_suggestion_memory_must_not_carry_field():
    with pytest.raises(ValueError):
        _suggestion(scope="memory", field="preferences")


def test_suggestion_rejects_bad_reason():
    with pytest.raises(ValueError):
        _suggestion(reason="bogus")


def test_suggestion_rejects_blank_summary():
    with pytest.raises(ValueError):
        _suggestion(summary="   ")


def test_report_new_and_roundtrip():
    suggestion = _suggestion()
    report = CuratorReport.new("审查完成", [suggestion])
    assert report.id.startswith("cur-")
    assert report.status == "open"
    assert CuratorReport.from_dict(report.to_dict()) == report


def test_report_rejects_bad_status():
    report = CuratorReport.new("x", [])
    report.status = "bogus"
    with pytest.raises(ValueError):
        CuratorReport.from_dict(report.to_dict())


def test_from_dict_requires_exact_fields():
    with pytest.raises(ValueError):
        CuratorSuggestion.from_dict({"id": "sug-1", "kind": "merge"})


def test_suggestion_skill_scope_valid():
    suggestion = _suggestion(scope="skill")
    assert suggestion.scope == "skill"


def test_suggestion_knowledge_scope_valid():
    suggestion = _suggestion(scope="knowledge")
    assert suggestion.scope == "knowledge"


def test_suggestion_skill_scope_rejects_field():
    with pytest.raises(ValueError):
        _suggestion(scope="skill", field="preferences")


def test_suggestion_expire_kind_allows_empty_keep():
    suggestion = _suggestion(kind="expire", scope="knowledge", keep="")
    assert suggestion.kind == "expire"
    assert suggestion.keep == ""


def test_suggestion_expire_requires_knowledge_scope():
    with pytest.raises(ValueError):
        _suggestion(kind="expire", scope="memory", keep="")
