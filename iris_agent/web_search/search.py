"""Web search client with multi-source fallback and retry."""

from __future__ import annotations

from dataclasses import replace
from inspect import signature
from urllib.parse import urlsplit, urlunsplit

from iris_agent.web_search.models import SearchOptions, SearchResult
from iris_agent.web_search.sources import BingSearchSource


class WebSearchClient:
    def __init__(
        self,
        timeout: float = 15,
        max_results: int = 5,
        max_snippet_chars: int = 300,
        enabled: bool = True,
        sources: list | None = None,
        max_retries: int = 2,
    ):
        self.timeout = timeout
        self.max_results = max_results
        self.max_snippet_chars = max_snippet_chars
        self.enabled = enabled
        self.max_retries = max(1, max_retries)
        self.last_error: str | None = None
        self.sources = sources if sources is not None else [
            BingSearchSource(timeout=timeout, max_snippet_chars=max_snippet_chars)
        ]

    def search(
        self,
        query: str,
        limit: int | None = None,
        options: SearchOptions | None = None,
    ) -> list[SearchResult]:
        self.last_error = None
        if not self.enabled:
            self.last_error = "联网搜索已禁用"
            return []
        if not self.sources:
            self.last_error = "没有可用搜索源"
            return []
        count = self.max_results if limit is None else min(limit, self.max_results)
        if count <= 0:
            return []
        errors: list[str] = []
        for source in self.sources:
            for _ in range(self.max_retries):
                try:
                    results = self._search_source(source, query, count, options)
                except ValueError:
                    self.last_error = (
                        f"{source.name} 该搜索源不支持请求的筛选条件（如时间范围）"
                    )
                    return []
                except Exception:
                    results = []
                if results:
                    normalized = self._deduplicate(results)
                    normalized.sort(
                        key=lambda result: (
                            result.score is None,
                            -(result.score if result.score is not None else 0),
                        )
                    )
                    return normalized[:count]
            errors.append(f"{source.name} 无结果")
        self.last_error = "; ".join(errors)
        return []

    @staticmethod
    def _search_source(source, query: str, count: int, options: SearchOptions | None):
        search = source.search
        try:
            search_signature = signature(search)
        except (TypeError, ValueError):
            return search(query, count, options)
        try:
            search_signature.bind(query, count, options)
        except TypeError:
            try:
                search_signature.bind(query, count, options=options)
            except TypeError:
                search_signature.bind(query, count)
                return search(query, count)
            return search(query, count, options=options)
        return search(query, count, options)

    @classmethod
    def _deduplicate(cls, results: list[SearchResult]) -> list[SearchResult]:
        unique: list[SearchResult] = []
        positions: dict[str, int] = {}
        for result in results:
            url = cls._normalize_url(result.url)
            candidate = replace(result, url=url)
            if url not in positions:
                positions[url] = len(unique)
                unique.append(candidate)
                continue
            position = positions[url]
            if cls._is_better(candidate, unique[position]):
                unique[position] = candidate
        return unique

    @staticmethod
    def _is_better(candidate: SearchResult, current: SearchResult) -> bool:
        if candidate.score != current.score:
            if candidate.score is None:
                return False
            if current.score is None:
                return True
            return candidate.score > current.score
        return len(candidate.snippet) > len(current.snippet)

    @staticmethod
    def _normalize_url(url: str) -> str:
        try:
            parts = urlsplit(url)
            scheme = parts.scheme.lower()
            if scheme not in {"http", "https"}:
                netloc = parts.netloc.rsplit("@", 1)[-1]
                return urlunsplit((scheme, netloc, parts.path, parts.query, ""))

            hostname = parts.hostname.lower() if parts.hostname else ""
            if ":" in hostname:
                hostname = f"[{hostname}]"
            port = parts.port
            if port is not None and not (
                (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
            ):
                hostname = f"{hostname}:{port}"
            path = parts.path.rstrip("/") or "/"
            return urlunsplit((scheme, hostname, path, parts.query, ""))
        except (TypeError, ValueError):
            return url.split("#", 1)[0]
