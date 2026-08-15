"""Knowledge service tests: add/list/get/delete/search orchestration."""

from __future__ import annotations

import pytest

from iris_agent.knowledge.embedder import EmbeddingError
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService


class FailingRetriever:
    def search(self, query, limit):
        raise EmbeddingError("embedding 不可用")


@pytest.fixture
def service(tmp_path):
    repository = KnowledgeRepository(tmp_path)
    retriever = KeywordRetriever(repository.list, max_hit_chars=500)
    return KnowledgeService(repository, retriever, max_content_chars=50000, default_limit=5)


def test_add_creates_entry(service):
    entry = service.add("多模态面试", "多模态大模型结构", category="面经")
    assert entry.id.startswith("kb-")
    assert entry.source_type == "manual"
    assert service.get(entry.id) == entry


def test_add_infers_scrape_from_url(service):
    entry = service.add("面试", "内容", source_url="https://example.com")
    assert entry.source_type == "scrape"
    assert entry.source_url == "https://example.com"


def test_add_truncates_content(service):
    entry = service.add("长文", "多模态" * 30000)
    assert len(entry.content) <= service.max_content_chars


def test_list_returns_entries(service):
    service.add("a", "内容a")
    service.add("b", "内容b")
    assert len(service.list()) == 2


def test_delete_removes_entry(service):
    entry = service.add("a", "内容")
    assert service.delete(entry.id) is True
    assert service.get(entry.id) is None


def test_search_returns_hits(service):
    entry = service.add("多模态面试", "多模态大模型结构")
    hits = service.search("多模态")
    assert len(hits) == 1
    assert hits[0].entry_id == entry.id


def test_search_respects_limit(service):
    for i in range(3):
        service.add(f"面经{i}", f"面经{i}内容")
    hits = service.search("面经", limit=1)
    assert len(hits) == 1


def test_search_falls_back_when_retriever_fails(tmp_path):
    repository = KnowledgeRepository(tmp_path)
    keyword = KeywordRetriever(repository.list, max_hit_chars=500)
    service = KnowledgeService(repository, FailingRetriever(), fallback_retriever=keyword)
    service.add("多模态面试", "多模态大模型结构")
    hits = service.search("多模态")
    assert len(hits) == 1


def test_search_reraises_without_fallback(tmp_path):
    repository = KnowledgeRepository(tmp_path)
    service = KnowledgeService(repository, FailingRetriever())
    with pytest.raises(EmbeddingError):
        service.search("多模态")
