"""Knowledge retrievers: pluggable search over knowledge entries."""

from __future__ import annotations

from typing import Callable, Protocol

from iris_agent.knowledge.models import KnowledgeEntry, KnowledgeSearchHit
from iris_agent.session_search.tokenizer import tokenize


class KnowledgeRetriever(Protocol):
    def search(self, query: str, limit: int) -> list[KnowledgeSearchHit]: ...


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
