"""Knowledge retrievers: pluggable search over knowledge entries."""

from __future__ import annotations

import hashlib
import math
from typing import Callable, Protocol

from iris_agent.knowledge.models import KnowledgeEntry, KnowledgeSearchHit
from iris_agent.session_search.tokenizer import tokenize


class KnowledgeRetriever(Protocol):
    def search(self, query: str, limit: int) -> list[KnowledgeSearchHit]: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class KeywordRetriever:
    """Match entries by CJK-bigram / word overlap between query and title+content."""

    def __init__(self, list_entries: Callable[[], list[KnowledgeEntry]], max_hit_chars: int = 500):
        self._list_entries = list_entries
        self.max_hit_chars = max_hit_chars

    def search(self, query: str, limit: int) -> list[KnowledgeSearchHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        candidates: list[tuple[int, float, KnowledgeSearchHit]] = []
        for entry in self._list_entries():
            doc_tokens = tokenize(entry.title) | tokenize(entry.content)
            score = len(query_tokens & doc_tokens)
            if score <= 0:
                continue
            candidates.append(
                (
                    score,
                    entry.updated_at,
                    KnowledgeSearchHit(
                        entry_id=entry.id,
                        title=entry.title,
                        content=entry.content[: self.max_hit_chars],
                        source_url=entry.source_url,
                        score=score,
                    ),
                )
            )
        candidates.sort(key=lambda item: (-item[0], -item[1]))
        return [hit for _, _, hit in candidates[:limit]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingRetriever:
    """Match entries by cosine similarity between query and entry vectors."""

    def __init__(
        self,
        list_entries: Callable[[], list[KnowledgeEntry]],
        embedder: Embedder,
        max_hit_chars: int = 500,
    ):
        self._list_entries = list_entries
        self._embedder = embedder
        self.max_hit_chars = max_hit_chars
        self._cache: dict[str, tuple[str, list[float]]] = {}

    def search(self, query: str, limit: int) -> list[KnowledgeSearchHit]:
        entries = self._list_entries()
        if not entries:
            return []
        [query_vec] = self._embedder.embed([query])
        scored: list[tuple[float, KnowledgeEntry]] = []
        for entry in entries:
            scored.append((_cosine(query_vec, self._vector_for(entry)), entry))
        scored.sort(key=lambda item: (-item[0], -item[1].updated_at))
        return [
            KnowledgeSearchHit(
                entry_id=entry.id,
                title=entry.title,
                content=entry.content[: self.max_hit_chars],
                source_url=entry.source_url,
                score=round(sim * 1000),
            )
            for sim, entry in scored[:limit]
        ]

    def _vector_for(self, entry: KnowledgeEntry) -> list[float]:
        text = f"{entry.title}\n{entry.content}"
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = self._cache.get(entry.id)
        if cached is not None and cached[0] == key:
            return cached[1]
        [vector] = self._embedder.embed([text])
        self._cache[entry.id] = (key, vector)
        return vector
