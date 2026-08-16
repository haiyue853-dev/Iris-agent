"""相似度引擎：embedding 余弦为主，bigram 重叠降级，按阈值分桶。"""

from __future__ import annotations

import math
from typing import Protocol

from iris_agent.session_search.tokenizer import tokenize

_DUPLICATE = "duplicate"
_REVIEW = "review"
_UNRELATED = "unrelated"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def bigram_overlap(a: str, b: str) -> float:
    """Jaccard 相似度 over tokenizer sets (CJK bigram + lowercase words)."""
    tokens_a = tokenize(a)
    tokens_b = tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def bucket(score: float, merge_threshold: float, conflict_threshold: float) -> str:
    if score > merge_threshold:
        return _DUPLICATE
    if score <= conflict_threshold:
        return _UNRELATED
    return _REVIEW


class SimilarityEngine:
    """Score text pairs in one batch and bucket them into duplicate/review/unrelated."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        merge_threshold: float = 0.85,
        conflict_threshold: float = 0.45,
    ):
        self.embedder = embedder
        self.merge_threshold = merge_threshold
        self.conflict_threshold = conflict_threshold

    def score_pairs(self, pairs: list[tuple[str, str]]) -> tuple[list[float], str]:
        """Score each (text_a, text_b) pair.

        Batch-embeds all unique texts once. Returns ``(scores, mode)`` where
        mode is ``"embedding"`` when vectors were used, or ``"overlap"`` on
        fallback.
        """
        unique: list[str] = []
        index: dict[str, int] = {}
        for a, b in pairs:
            for text in (a, b):
                if text not in index:
                    index[text] = len(unique)
                    unique.append(text)

        vectors: list[list[float]] | None = None
        mode = "overlap"
        if self.embedder is not None:
            try:
                vectors = self.embedder.embed(unique)
                mode = "embedding"
            except Exception:
                vectors = None

        scores: list[float] = []
        for a, b in pairs:
            if vectors is not None:
                scores.append(cosine(vectors[index[a]], vectors[index[b]]))
            else:
                scores.append(bigram_overlap(a, b))
        return scores, mode

    def bucket(self, score: float) -> str:
        return bucket(score, self.merge_threshold, self.conflict_threshold)
