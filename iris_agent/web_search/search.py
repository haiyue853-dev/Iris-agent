"""Web search client with multi-source fallback and retry."""

from __future__ import annotations

from iris_agent.web_search.models import SearchResult
from iris_agent.web_search.sources import BingSearchSource


class WebSearchClient:
    def __init__(
        self,
        timeout: float = 15,
        max_results: int = 5,
        max_snippet_chars: int = 300,
        enabled: bool = True,
        sources: list | None = None,
    ):
        self.timeout = timeout
        self.max_results = max_results
        self.max_snippet_chars = max_snippet_chars
        self.enabled = enabled
        self.last_error: str | None = None
        self.sources = sources or [BingSearchSource(timeout=timeout, max_snippet_chars=max_snippet_chars)]

    def search(self, query: str, limit: int | None = None) -> list[SearchResult]:
        self.last_error = None
        if not self.enabled:
            self.last_error = "联网搜索已禁用"
            return []
        count = limit or self.max_results
        errors: list[str] = []
        for source in self.sources:
            for _ in range(2):  # 每个源重试 1 次，处理偶发网络失败
                results = source.search(query, count)
                if results:
                    return results
            errors.append(f"{source.name} 无结果")
        self.last_error = "; ".join(errors)
        return []
