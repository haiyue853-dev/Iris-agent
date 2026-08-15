"""Knowledge service: orchestrate add/list/get/delete/search over the knowledge base."""

from __future__ import annotations

from iris_agent.knowledge.models import KnowledgeEntry, KnowledgeSearchHit
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KnowledgeRetriever


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        retriever: KnowledgeRetriever,
        max_content_chars: int = 50000,
        default_limit: int = 5,
    ):
        self.repository = repository
        self.retriever = retriever
        self.max_content_chars = max_content_chars
        self.default_limit = default_limit

    def add(
        self,
        title: str,
        content: str,
        *,
        category: str = "面经",
        source_url: str | None = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry.new(
            title=title,
            content=content[: self.max_content_chars],
            category=category,
            source_url=source_url,
            source_type="scrape" if source_url else "manual",
        )
        self.repository.save(entry)
        return entry

    def list(self) -> list[KnowledgeEntry]:
        return self.repository.list()

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        return self.repository.get(entry_id)

    def delete(self, entry_id: str) -> bool:
        return self.repository.delete(entry_id)

    def search(self, query: str, limit: int | None = None) -> list[KnowledgeSearchHit]:
        return self.retriever.search(query, limit or self.default_limit)
