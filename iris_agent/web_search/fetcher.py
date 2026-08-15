"""Page fetcher: fetch a web page and extract readable text (with SSRF guards)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_RETRY_STATUS = frozenset({521, 403, 429})

_REMOVED_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript", "iframe")
_BODY_SELECTORS = ("article", "#article_content", "#content_views", "main", ".article-content", ".post-content", ".markdown-body")


class PageFetcher:
    def __init__(
        self,
        timeout: float = 15,
        max_page_chars: int = 30000,
        enabled: bool = True,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ):
        self.timeout = timeout
        self.max_page_chars = max_page_chars
        self.enabled = enabled
        self.max_retries = max_retries
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch(self, url: str) -> str:
        if not self.enabled:
            raise ValueError("联网抓取已禁用")
        self._validate_url(url)
        last_detail: object | None = None
        for attempt in range(self.max_retries + 1):
            headers = self._headers_for(attempt, url)
            try:
                response = self._client.get(url, headers=headers)
            except Exception as exc:
                last_detail = exc
                continue
            if response.status_code in _RETRY_STATUS:
                last_detail = f"HTTP {response.status_code}"
                continue
            if response.status_code >= 400:
                raise ValueError(f"网页抓取失败: HTTP {response.status_code}")
            return self._extract_text(response.text)[: self.max_page_chars]
        raise ValueError(f"网页抓取失败: {last_detail}")

    @staticmethod
    def _headers_for(attempt: int, url: str) -> dict[str, str]:
        headers = dict(_HEADERS)
        if attempt > 0:
            headers["User-Agent"] = _MOBILE_UA
        headers["Referer"] = PageFetcher._referer(url)
        return headers

    @staticmethod
    def _referer(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("仅支持 http/https 链接")
        host = parsed.hostname
        if not host:
            raise ValueError("无效链接")
        lowered = host.lower()
        if lowered == "localhost" or lowered.endswith((".local", ".internal", ".localhost")):
            raise ValueError("禁止访问内网地址")
        try:
            ip = ipaddress.ip_address(lowered)
        except ValueError:
            return  # 普通域名，放行
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("禁止访问内网地址")

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for selector in _BODY_SELECTORS:
            node = soup.select_one(selector)
            if node is not None:
                for tag in node(_REMOVED_TAGS):
                    tag.decompose()
                return PageFetcher._clean_text(node.get_text(separator="\n", strip=True))
        for tag in soup(_REMOVED_TAGS):
            tag.decompose()
        return PageFetcher._clean_text(soup.get_text(separator="\n", strip=True))

    @staticmethod
    def _clean_text(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
