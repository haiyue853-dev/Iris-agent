"""Bing web search client (free, no API key)."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from iris_agent.web_search.models import SearchResult

_SEARCH_URL = "https://www.bing.com/search"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


class WebSearchClient:
    def __init__(
        self,
        timeout: float = 15,
        max_results: int = 5,
        max_snippet_chars: int = 300,
        enabled: bool = True,
        http_client: httpx.Client | None = None,
    ):
        self.timeout = timeout
        self.max_results = max_results
        self.max_snippet_chars = max_snippet_chars
        self.enabled = enabled
        self.last_error: str | None = None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, query: str, limit: int | None = None) -> list[SearchResult]:
        self.last_error = None
        if not self.enabled:
            self.last_error = "联网搜索已禁用"
            return []
        count = limit or self.max_results
        try:
            response = self._client.get(
                _SEARCH_URL,
                params={"q": query, "count": count},
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
        except Exception as exc:
            self.last_error = f"搜索请求失败: {exc}"
            return []
        return self._parse(response.text, count)

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
