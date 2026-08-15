from pathlib import Path

import pytest

from iris_agent.memory.models import MemoryEntry
from iris_agent.memory.repository import MemoryLedgerError, MemoryRepository


def test_repository_roundtrips_entries(tmp_path: Path) -> None:
    repo = MemoryRepository(tmp_path)
    entry = MemoryEntry.new("用户偏好中文回答", "preference")
    repo.save([entry])
    loaded = repo.load()
    assert len(loaded) == 1
    assert loaded[0].id == entry.id
    assert loaded[0].content == "用户偏好中文回答"
    assert loaded[0].category == "preference"


def test_repository_returns_empty_when_missing(tmp_path: Path) -> None:
    repo = MemoryRepository(tmp_path)
    assert repo.load() == []


def test_repository_rejects_malformed_ledger(tmp_path: Path) -> None:
    repo = MemoryRepository(tmp_path)
    (tmp_path / "memory.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(MemoryLedgerError):
        repo.load()


def test_repository_rejects_unknown_payload_shape(tmp_path: Path) -> None:
    repo = MemoryRepository(tmp_path)
    (tmp_path / "memory.json").write_text('{"wrong": []}', encoding="utf-8")
    with pytest.raises(MemoryLedgerError):
        repo.load()


def test_entry_validation_rejects_blank_content() -> None:
    with pytest.raises(ValueError):
        MemoryEntry.new("", "fact")


def test_entry_validation_rejects_unknown_category() -> None:
    with pytest.raises(ValueError):
        MemoryEntry.new("内容", "unknown")


def test_entry_validation_rejects_oversized_content() -> None:
    with pytest.raises(ValueError):
        MemoryEntry.new("长" * 501, "fact")


def test_from_dict_rejects_extra_fields() -> None:
    data = {
        "id": "memory_x",
        "content": "内容",
        "category": "fact",
        "created_at": "2026-08-15T00:00:00+00:00",
        "updated_at": "2026-08-15T00:00:00+00:00",
        "source_session_id": None,
        "secret": "must not persist",
    }
    with pytest.raises(ValueError):
        MemoryEntry.from_dict(data)
