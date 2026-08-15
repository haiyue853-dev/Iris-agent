"""HybridRetriever tests: RRF fusion and deduplication."""

from __future__ import annotations

from iris_agent.knowledge.models import KnowledgeSearchHit
from iris_agent.knowledge.retriever import HybridRetriever


def _hit(entry_id: str, title: str) -> KnowledgeSearchHit:
    return KnowledgeSearchHit(
        entry_id=entry_id,
        title=title,
        content=f"{title}内容",
        source_url=None,
        score=1,
    )


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, limit):
        return self.hits[:limit]


def test_hybrid_retriever_rrf_ranking():
    keyword = FakeRetriever([
        _hit("kb-000000000001", "A"),
        _hit("kb-000000000002", "B"),
    ])
    embedding = FakeRetriever([
        _hit("kb-000000000002", "B"),
    ])
    hybrid = HybridRetriever(keyword, embedding)
    hits = hybrid.search("query", 5)
    assert hits[0].entry_id == "kb-000000000002"


def test_hybrid_retriever_deduplicates():
    keyword = FakeRetriever([_hit("kb-000000000001", "A")])
    embedding = FakeRetriever([_hit("kb-000000000001", "A")])
    hybrid = HybridRetriever(keyword, embedding)
    hits = hybrid.search("query", 5)
    assert len(hits) == 1


def test_hybrid_retriever_respects_limit():
    keyword = FakeRetriever([_hit("kb-000000000001", "A")])
    embedding = FakeRetriever([_hit("kb-000000000002", "B")])
    hybrid = HybridRetriever(keyword, embedding)
    hits = hybrid.search("query", 1)
    assert len(hits) == 1
