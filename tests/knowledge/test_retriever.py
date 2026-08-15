"""Keyword retriever tests: scoring, ranking, truncation, limits."""

from __future__ import annotations

from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.retriever import KeywordRetriever


def _entry(**overrides) -> KnowledgeEntry:
    fields: dict = {
        "id": "kb-000000000001",
        "title": "多模态大模型",
        "content": "多模态大模型结构包括视觉编码器和文本编码器",
        "category": "面经",
        "source_url": None,
        "source_type": "manual",
        "created_at": 1000.0,
        "updated_at": 1000.0,
    }
    fields.update(overrides)
    return KnowledgeEntry(**fields)


def _retriever(entries) -> KeywordRetriever:
    return KeywordRetriever(lambda: entries, max_hit_chars=500)


def test_keyword_retriever_returns_matching_hits():
    retriever = _retriever([_entry()])
    hits = retriever.search("多模态", 5)
    assert len(hits) == 1
    assert hits[0].entry_id == "kb-000000000001"
    assert hits[0].score > 0


def test_keyword_retriever_returns_empty_for_no_match():
    retriever = _retriever([_entry()])
    assert retriever.search("完全不相关词", 5) == []


def test_keyword_retriever_ranks_higher_score_first():
    entries = [
        _entry(id="kb-000000000001", title="多模态", content="多模态大模型"),
        _entry(id="kb-000000000002", title="多模态存储", content="多模态 用户信息 存储 方式"),
    ]
    hits = _retriever(entries).search("多模态 存储", 5)
    assert hits[0].entry_id == "kb-000000000002"


def test_keyword_retriever_truncates_content():
    retriever = KeywordRetriever(lambda: [_entry(content="多模态" * 1000)], max_hit_chars=500)
    hits = retriever.search("多模态", 5)
    assert hits[0].score > 0
    assert len(hits[0].content) <= 500


def test_keyword_retriever_empty_query_returns_empty():
    retriever = _retriever([_entry()])
    assert retriever.search("", 5) == []
    assert retriever.search("   ", 5) == []


def test_keyword_retriever_respects_limit():
    entries = [_entry(id=f"kb-{i:012x}", title=f"面经{i}") for i in range(5)]
    hits = _retriever(entries).search("面经", 2)
    assert len(hits) == 2
