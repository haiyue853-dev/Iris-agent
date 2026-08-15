"""EmbeddingRetriever tests: similarity ranking, caching, truncation."""

from __future__ import annotations

from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.retriever import EmbeddingRetriever


def _entry(**overrides) -> KnowledgeEntry:
    fields: dict = {
        "id": "kb-000000000001",
        "title": "A",
        "content": "内容A",
        "category": "面经",
        "source_url": None,
        "source_type": "manual",
        "created_at": 1000.0,
        "updated_at": 1000.0,
    }
    fields.update(overrides)
    return KnowledgeEntry(**fields)


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [self.vectors[text] for text in texts]


def test_embedding_retriever_returns_hits():
    embedder = FakeEmbedder({"A\n内容A": [1.0, 0.0], "多模态": [1.0, 0.0]})
    retriever = EmbeddingRetriever(lambda: [_entry()], embedder)
    hits = retriever.search("多模态", 5)
    assert len(hits) == 1
    assert hits[0].entry_id == "kb-000000000001"
    assert hits[0].score > 0


def test_embedding_retriever_ranks_by_similarity():
    entries = [
        _entry(id="kb-000000000001", title="A", content="内容A"),
        _entry(id="kb-000000000002", title="B", content="内容B"),
    ]
    embedder = FakeEmbedder({
        "A\n内容A": [1.0, 0.0],
        "B\n内容B": [0.0, 1.0],
        "多模态": [1.0, 0.0],
    })
    hits = EmbeddingRetriever(lambda: entries, embedder).search("多模态", 5)
    assert hits[0].entry_id == "kb-000000000001"


def test_embedding_retriever_caches_vectors():
    entries = [_entry(id="kb-000000000001", title="A", content="内容A")]
    embedder = FakeEmbedder({
        "A\n内容A": [1.0, 0.0],
        "多模态": [1.0, 0.0],
        "别的查询": [1.0, 0.0],
    })
    retriever = EmbeddingRetriever(lambda: entries, embedder)
    retriever.search("多模态", 5)
    retriever.search("别的查询", 5)
    entry_embeds = [texts for texts in embedder.calls if texts == ["A\n内容A"]]
    assert len(entry_embeds) == 1


def test_embedding_retriever_reembeds_changed_content():
    entries = [_entry(id="kb-000000000001", title="A", content="内容A")]
    embedder = FakeEmbedder({
        "A\n内容A": [1.0, 0.0],
        "A\n内容B": [0.0, 1.0],
        "多模态": [1.0, 0.0],
    })
    retriever = EmbeddingRetriever(lambda: entries, embedder)
    retriever.search("多模态", 5)
    entries[0] = _entry(id="kb-000000000001", title="A", content="内容B")
    retriever.search("多模态", 5)
    entry_embeds = [texts for texts in embedder.calls if texts[0].startswith("A\n")]
    assert len(entry_embeds) == 2


def test_embedding_retriever_empty_entries():
    retriever = EmbeddingRetriever(lambda: [], FakeEmbedder({"多模态": [1.0, 0.0]}))
    assert retriever.search("多模态", 5) == []
