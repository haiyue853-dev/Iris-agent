"""相似度引擎测试：余弦/bigram 降级/分桶/批量打分。"""

from __future__ import annotations

import pytest

from iris_agent.curator.similarity import (
    SimilarityEngine,
    bigram_overlap,
    bucket,
    cosine,
)


def test_cosine_identical():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_norm():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_bigram_overlap_identical():
    assert bigram_overlap("多模态存储", "多模态存储") == pytest.approx(1.0)


def test_bigram_overlap_disjoint():
    assert bigram_overlap("苹果", "香蕉") == pytest.approx(0.0)


def test_bucket_boundaries():
    assert bucket(0.9, 0.85, 0.45) == "duplicate"
    assert bucket(0.6, 0.85, 0.45) == "review"
    assert bucket(0.3, 0.85, 0.45) == "unrelated"
    assert bucket(0.45, 0.85, 0.45) == "unrelated"  # 含下界算无关


class FakeEmbedder:
    def __init__(self, vectors=None, error=False):
        self._vectors = vectors or {}
        self.error = error
        self.embed_calls: list[list[str]] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        if self.error:
            raise RuntimeError("embed failed")
        return [self._vectors.get(t, [1.0, 0.0]) for t in texts]


def test_score_pairs_uses_embedding():
    engine = SimilarityEngine(embedder=FakeEmbedder())
    scores, mode = engine.score_pairs([("a", "a")])
    assert mode == "embedding"
    assert scores == pytest.approx([1.0])


def test_score_pairs_batches_unique_texts():
    embedder = FakeEmbedder()
    engine = SimilarityEngine(embedder=embedder)
    engine.score_pairs([("a", "b"), ("b", "c")])
    assert embedder.embed_calls == [["a", "b", "c"]]


def test_score_pairs_falls_back_on_embed_error():
    engine = SimilarityEngine(embedder=FakeEmbedder(error=True))
    scores, mode = engine.score_pairs([("多模态存储", "多模态存储")])
    assert mode == "overlap"
    assert scores == pytest.approx([1.0])


def test_score_pairs_falls_back_without_embedder():
    engine = SimilarityEngine(embedder=None)
    scores, mode = engine.score_pairs([("多模态存储", "多模态存储")])
    assert mode == "overlap"
    assert scores == pytest.approx([1.0])
