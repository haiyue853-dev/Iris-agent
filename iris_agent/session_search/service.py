"""Session search service: scan sessions and rank matching message fragments."""

from __future__ import annotations

from iris_agent.sessions.base import SessionRepository
from iris_agent.session_search.models import SearchHit
from iris_agent.session_search.tokenizer import tokenize

_SEARCHABLE_ROLES = {"user", "assistant"}


class SessionSearchService:
    def __init__(self, sessions: SessionRepository, max_hit_chars: int = 300, default_limit: int = 5):
        self.sessions = sessions
        self.max_hit_chars = max_hit_chars
        self.default_limit = default_limit

    def search(self, query: str, limit: int | None = None) -> list[SearchHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        limit = limit or self.default_limit
        hits: list[SearchHit] = []
        for session in self.sessions.list():
            for message in session.messages:
                if message.role not in _SEARCHABLE_ROLES:
                    continue
                if not message.content or not message.content.strip():
                    continue
                score = len(query_tokens & tokenize(message.content))
                if score <= 0:
                    continue
                hits.append(
                    SearchHit(
                        session_id=session.id,
                        session_name=session.name,
                        role=message.role,
                        content=message.content,
                        updated_at=session.updated_at,
                        score=score,
                    )
                )
        hits.sort(key=lambda hit: (-hit.score, -hit.updated_at))
        return hits[:limit]
