"""Pluggable search sources (Bing + DuckDuckGo)."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from iris_agent.web_search.models import SearchResult

_BING_URL = "https://www.bing.com/search"
_DDG_URL = "https://html.duckduckgo.com/html/"

_COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class BingSearchSource:
    name = "bing"

    def __init__(self, timeout: float = 15, max_snippet_chars: int = 300, http_client: httpx.Client | None = None):
        self.timeout = timeout
        self.max_snippet_chars = max_snippet_chars
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, query: str, limit: int) -> list[SearchResult]:
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
            results.append(SearchResult(title=title, url=url, snippet=snippet[: self.max_snippet_chars]))
        return results


class DuckDuckGoSearchSource:
    name = "duckduckgo"

    def __init__(self, timeout: float = 15, max_snippet_chars: int = 300, http_client: httpx.Client | None = None):
        self.timeout = timeout
        self.max_snippet_chars = max_snippet_chars
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, query: str, limit: int) -> list[SearchResult]:
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
            results.append(SearchResult(title=title, url=url, snippet=snippet[: self.max_snippet_chars]))
        return results
