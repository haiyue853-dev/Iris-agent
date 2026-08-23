"""Pluggable web search sources."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from iris_agent.web_search.models import SearchOptions, SearchResult

_BING_URL = "https://www.bing.com/search"
_DDG_URL = "https://html.duckduckgo.com/html/"
_TAVILY_URL = "https://api.tavily.com/search"

_COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _html_search_query(query: str, options: SearchOptions | None) -> str:
    if options is None:
        return query
    if options.time_range is not None:
        raise ValueError("time_range is not supported by HTML search sources")
    parts = [query]
    if options.topic == "news":
        parts.append("news")
    if options.include_domains:
        included = " OR ".join(f"site:{domain}" for domain in options.include_domains)
        parts.append(f"({included})")
    parts.extend(f"-site:{domain}" for domain in options.exclude_domains)
    return " ".join(parts)


class BingSearchSource:
    name = "bing"
    supports_options = frozenset({"topic", "include_domains", "exclude_domains"})

    def __init__(self, timeout: float = 15, max_snippet_chars: int = 300, http_client: httpx.Client | None = None):
        self.timeout = timeout
        self.max_snippet_chars = max_snippet_chars
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search(self, query: str, limit: int, options: SearchOptions | None = None) -> list[SearchResult]:
        query = _html_search_query(query, options)
        try:
            response = self._client.get(
                _BING_URL,
                params={"q": query, "count": limit},
                headers={"User-Agent": _DESKTOP_UA, **_COMMON_HEADERS},
            )
            response.raise_for_status()
        except Exception:
            return []
        return self._parse(response.text, limit)

    def _parse(self, html: str, limit: int) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []
        for item in soup.select("li.b_algo"):
            if len(results) >= limit:
                break
            anchor = item.select_one("h2 a")
            if anchor is None:
                continue
            title = anchor.get_text(strip=True)
            url = anchor.get("href", "").strip()
            if not title or not url:
                continue
            snippet_el = item.select_one("p") or item.select_one("div.b_caption p")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet[: self.max_snippet_chars],
                    source=self.name,
                )
            )
        return results


class DuckDuckGoSearchSource:
    name = "duckduckgo"
    supports_options = frozenset({"topic", "include_domains", "exclude_domains"})

    def __init__(self, timeout: float = 15, max_snippet_chars: int = 300, http_client: httpx.Client | None = None):
        self.timeout = timeout
        self.max_snippet_chars = max_snippet_chars
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search(self, query: str, limit: int, options: SearchOptions | None = None) -> list[SearchResult]:
        query = _html_search_query(query, options)
        try:
            response = self._client.get(
                _DDG_URL,
                params={"q": query},
                headers={"User-Agent": _DESKTOP_UA, **_COMMON_HEADERS},
            )
            response.raise_for_status()
        except Exception:
            return []
        return self._parse(response.text, limit)

    def _parse(self, html: str, limit: int) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []
        for item in soup.select("div.result"):
            if len(results) >= limit:
                break
            anchor = item.select_one("a.result__a")
            if anchor is None:
                continue
            title = anchor.get_text(strip=True)
            url = anchor.get("href", "").strip()
            if not title or not url:
                continue
            snippet_el = item.select_one("a.result__snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet[: self.max_snippet_chars],
                    source=self.name,
                )
            )
        return results


class TavilySearchSource:
    name = "tavily"

    def __init__(
        self,
        api_key: str,
        timeout: float = 15,
        max_snippet_chars: int = 300,
        http_client: httpx.Client | None = None,
        endpoint: str = _TAVILY_URL,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.max_snippet_chars = max_snippet_chars
        self.endpoint = endpoint
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search(self, query: str, limit: int, options: SearchOptions | None = None) -> list[SearchResult]:
        options = options or SearchOptions()
        payload: dict[str, object] = {
            "query": query,
            "max_results": limit,
            "topic": options.topic,
            "search_depth": options.search_depth,
        }
        if options.time_range:
            payload["time_range"] = options.time_range
        if options.include_domains:
            payload["include_domains"] = list(options.include_domains)
        if options.exclude_domains:
            payload["exclude_domains"] = list(options.exclude_domains)

        try:
            response = self._client.post(
                self.endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            return []

        results: list[SearchResult] = []
        for item in data["results"]:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(url, str) or not url.strip():
                continue
            content = item.get("content")
            snippet = content if isinstance(content, str) else ""
            published_date = item.get("published_date")
            if not isinstance(published_date, str):
                published_date = None
            score = item.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                score = None
            else:
                score = float(score)
            results.append(
                SearchResult(
                    title=title.strip(),
                    url=url.strip(),
                    snippet=snippet[: self.max_snippet_chars],
                    source=self.name,
                    published_date=published_date,
                    score=score,
                )
            )
        return results
