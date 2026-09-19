"""Web search client with multi-source fallback and retry."""

from __future__ import annotations

from dataclasses import replace
from inspect import signature
from threading import local
from time import monotonic

from iris_agent.tools.context import remaining, report_progress
from iris_agent.tools.base import ToolInvocationError
from iris_agent.web_search.errors import classify_search_error, SearchSourceError
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
        self._state = local()
        self.sources = sources if sources is not None else [
            BingSearchSource(timeout=timeout, max_snippet_chars=max_snippet_chars)
        ]

    @property
    def last_error(self):
        return getattr(self._state, "error", None)

    @property
    def last_error_code(self):
        return getattr(self._state, "code", None)

    @property
    def last_metadata(self):
        return getattr(self._state, "metadata", {})

    def search(self, query: str, limit: int | None = None,
               options: SearchOptions | None = None) -> list[SearchResult]:
        started = monotonic()
        deadline = started + self.timeout
        self._state.error = self._state.code = None
        attempts = []
        self._state.metadata = {"attempts": attempts, "status": "empty"}
        count = self.max_results if limit is None else min(limit, self.max_results)
        requested = self._requested_options(options)
        empty = False
        failure = None
        try:
            if not self.enabled or not self.sources:
                failure = SearchSourceError("search_unavailable", "联网搜索已禁用" if not self.enabled else "没有可用搜索源")
                return []
            if count <= 0:
                return []
            for source in self.sources:
                name = source.name
                supported = getattr(source, "supports_options", None)
                if not getattr(source, "is_available", True):
                    failure = SearchSourceError("search_unavailable", "搜索源未配置")
                    attempts.append({"source": name, "status": "skipped", "error_code": failure.code})
                    continue
                if supported is not None and requested - supported:
                    failure = SearchSourceError("search_unsupported_options", "该搜索源不支持请求的筛选条件（如时间范围）")
                    attempts.append({"source": name, "status": "skipped", "error_code": failure.code})
                    continue
                for attempt in range(self.max_retries):
                    seconds = remaining(deadline)
                    report_progress(phase="searching", source=name, attempt=attempt + 1)
                    try:
                        results = self._search_source(source, query, count, options, seconds)
                        remaining(deadline)
                    except ToolInvocationError:
                        raise
                    except Exception as exc:
                        failure = classify_search_error(exc)
                        attempts.append({"source": name, "status": "failed", "error_code": failure.code})
                        if failure.retryable and attempt + 1 < self.max_retries:
                            continue
                        break
                    if not results:
                        empty = True
                        attempts.append({"source": name, "status": "empty"})
                        break
                    normalized = self._deduplicate(results)
                    normalized.sort(key=lambda result: (result.score is None, -(result.score or 0)))
                    attempts.append({"source": name, "status": "success"})
                    self._state.metadata.update(source=name, status="success")
                    failure = None
                    return normalized[:count]
            return []
        except ToolInvocationError as exc:
            failure = SearchSourceError(exc.code, str(exc))
            empty = False
            return []
        finally:
            if failure is not None and not empty:
                self._state.error, self._state.code = str(failure), failure.code
                self._state.metadata["status"] = "failed"
            self._state.metadata["duration_ms"] = round((monotonic() - started) * 1000)

    @staticmethod
    def _requested_options(options):
        if options is None:
            return set()
        defaults = SearchOptions()
        return {name for name in ("topic", "time_range", "include_domains", "exclude_domains", "search_depth")
                if getattr(options, name) != getattr(defaults, name)}

    @staticmethod
    def _search_source(source, query, count, options, timeout):
        search = source.search
        try:
            parameters = signature(search)
        except (TypeError, ValueError):
            return search(query, count, options)
        timeout_kwargs = {"timeout": timeout} if "timeout" in parameters.parameters else {}
        candidates = [((query, count, options), timeout_kwargs),
                      ((query, count), {**timeout_kwargs, "options": options})]
        if not WebSearchClient._requested_options(options):
            candidates.append(((query, count), timeout_kwargs))
        for args, kwargs in candidates:
            try:
                parameters.bind(*args, **kwargs)
            except TypeError:
                continue
            return search(*args, **kwargs)
        raise SearchSourceError("search_unsupported_options", "该搜索源不支持请求的筛选条件（如时间范围）")

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
