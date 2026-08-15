"""Page fetcher: fetch a web page and extract readable text (with SSRF guards)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

_REMOVED_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript", "iframe")


class PageFetcher:
    def __init__(
        self,
        timeout: float = 15,
        max_page_chars: int = 8000,
        enabled: bool = True,
        http_client: httpx.Client | None = None,
    ):
        self.timeout = timeout
        self.max_page_chars = max_page_chars
        self.enabled = enabled
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch(self, url: str) -> str:
        if not self.enabled:
            raise ValueError("联网抓取已禁用")
        self._validate_url(url)
        try:
            response = self._client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"网页抓取失败: {exc}") from exc
        return self._extract_text(response.text)[: self.max_page_chars]

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
        for tag in soup(_REMOVED_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
