from pathlib import Path

import pytest

from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryNotFoundError, MemoryService


@pytest.fixture
def service(tmp_path: Path) -> MemoryService:
    return MemoryService(MemoryRepository(tmp_path), max_entries=20)


def test_add_list_delete_lifecycle(service: MemoryService) -> None:
    entry = service.add("用户偏好中文", "preference")
    assert entry.category == "preference"
    assert [e.id for e in service.list()] == [entry.id]

    service.delete(entry.id)
    assert service.list() == []


def test_add_rejects_blank_and_unknown_category(service: MemoryService) -> None:
    with pytest.raises(ValueError):
        service.add("", "fact")
    with pytest.raises(ValueError):
        service.add("内容", "unknown")


def test_delete_missing_raises(service: MemoryService) -> None:
    with pytest.raises(MemoryNotFoundError):
        service.delete("memory_missing")


def test_add_evicts_oldest_when_over_capacity(service: MemoryService) -> None:
    for i in range(25):
        service.add(f"事实 {i}", "fact")
    entries = service.list()
    contents = {e.content for e in entries}
    assert len(entries) == 20
    assert "事实 24" in contents
    assert "事实 0" not in contents


def test_inject_respects_entry_and_char_caps(service: MemoryService) -> None:
    service.add("用户偏好中文回答" * 10, "preference")
    service.add("另一个偏好", "preference")
    injected = service.inject()
    assert len(injected) <= 20
    assert sum(len(e.content) for e in injected) <= 2000


def test_inject_is_empty_when_no_memory(service: MemoryService) -> None:
    assert service.inject() == []


def test_inject_orders_most_recent_first(service: MemoryService) -> None:
    service.add("较早的记忆", "fact")
    service.add("最新的记忆", "fact")
    assert [e.content for e in service.inject()] == ["最新的记忆", "较早的记忆"]


def test_add_rejects_content_over_service_limit(tmp_path: Path) -> None:
    limited = MemoryService(MemoryRepository(tmp_path), max_chars=10)
    with pytest.raises(ValueError):
        limited.add("长" * 11, "fact")
