"""Knowledge repository tests: model validation + per-entry file persistence."""

from __future__ import annotations

import pytest

from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.repository import KnowledgeRepository, KnowledgeRepositoryError


def _entry(**overrides) -> KnowledgeEntry:
    fields: dict = {
        "id": "kb-0123456789ab",
        "title": "测试面经",
        "content": "这是正文",
        "category": "面经",
        "source_url": None,
        "source_type": "manual",
        "created_at": 1000.0,
        "updated_at": 1000.0,
    }
    fields.update(overrides)
    return KnowledgeEntry(**fields)


def test_entry_new_generates_id_and_timestamps():
    entry = KnowledgeEntry.new(title="标题", content="内容")
    assert entry.id.startswith("kb-")
    assert len(entry.id) == 15  # kb- + 12 hex
    assert entry.created_at > 0
    assert entry.updated_at == entry.created_at
    assert entry.source_type == "manual"


def test_entry_roundtrip_through_dict():
    entry = _entry()
    assert KnowledgeEntry.from_dict(entry.to_dict()) == entry


def test_entry_rejects_blank_title():
    with pytest.raises(ValueError):
        KnowledgeEntry.new(title="   ", content="内容")


def test_entry_rejects_too_long_content():
    with pytest.raises(ValueError):
        KnowledgeEntry.new(title="标题", content="x" * 50001)


def test_entry_rejects_invalid_source_type():
    with pytest.raises(ValueError):
        _entry(source_type="bogus")


def test_repository_save_and_get_roundtrip(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    entry = _entry(id="kb-000000000001")
    repo.save(entry)
    assert repo.get("kb-000000000001") == entry


def test_repository_list_returns_all(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    repo.save(_entry(id="kb-000000000001", title="a"))
    repo.save(_entry(id="kb-000000000002", title="b"))
    assert {e.id for e in repo.list()} == {"kb-000000000001", "kb-000000000002"}


def test_repository_delete_removes(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    repo.save(_entry(id="kb-000000000001"))
    assert repo.delete("kb-000000000001") is True
    assert repo.get("kb-000000000001") is None


def test_repository_get_missing_returns_none(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    assert repo.get("kb-ffffffffffff") is None


def test_repository_ignores_corrupt_files(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    (tmp_path / "notes.txt").write_text("not json", encoding="utf-8")
    (tmp_path / "bad.json").write_text("{invalid", encoding="utf-8")
    repo.save(_entry(id="kb-000000000001"))
    assert {e.id for e in repo.list()} == {"kb-000000000001"}


def test_repository_rejects_path_traversal_id(tmp_path):
    repo = KnowledgeRepository(tmp_path)
    with pytest.raises(KnowledgeRepositoryError):
        repo.get("../etc/passwd")


def test_from_dict_requires_exact_fields():
    with pytest.raises(ValueError):
        KnowledgeEntry.from_dict({"id": "kb-1", "title": "t"})
