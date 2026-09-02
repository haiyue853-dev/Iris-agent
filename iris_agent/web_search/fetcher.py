"""Page fetcher: fetch a web page and extract readable text (with SSRF guards)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
import httpcore
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_RETRY_STATUS = frozenset({521, 403, 429})

_REMOVED_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript", "iframe")
_BODY_SELECTORS = ("article", "#article_content", "#content_views", "main", ".article-content", ".post-content", ".markdown-body")
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5
_FULL_CONTENT_MAX_CHARS = 50_000


class UnsafeUrlError(ValueError):
    """The requested URL could reach a non-public network address."""


class PageTooLargeError(ValueError):
    """The response body exceeds the configured resource limit."""


def resolve_url(url: str, resolver=socket.getaddrinfo) -> tuple[str, list[ipaddress.IPv4Address | ipaddress.IPv6Address]]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("仅支持 http/https 链接")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("无效链接")
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith((".local", ".internal", ".localhost")):
        raise UnsafeUrlError("禁止访问内网地址")

    try:
        literal = ipaddress.ip_address(lowered)
        addresses = [literal]
    except ValueError:
        try:
            results = resolver(host, None, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(result[4][0]) for result in results]
        except (OSError, ValueError, TypeError, IndexError) as exc:
            raise UnsafeUrlError(f"DNS 解析失败: {host}") from exc
        if not addresses:
            raise UnsafeUrlError(f"DNS 解析失败: {host}")

    if any(
        not address.is_global
        or (isinstance(address, ipaddress.IPv6Address) and address.is_site_local)
        for address in addresses
    ):
        raise UnsafeUrlError("禁止访问内网地址")
    return lowered, addresses


def validate_url(url: str, resolver=socket.getaddrinfo) -> None:
    resolve_url(url, resolver)


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, pins: dict[str, str], backend=None):
        self._pins = pins
        self._backend = backend or httpcore.SyncBackend()

    def connect_tcp(self, host, port, **kwargs):
        pinned = self._pins.get(host.lower())
        if pinned is None:
            raise UnsafeUrlError(f"主机尚未经过安全解析: {host}")
        return self._backend.connect_tcp(pinned, port, **kwargs)

    def connect_unix_socket(self, path, **kwargs):
        raise UnsafeUrlError("禁止 Unix socket 抓取")

    def sleep(self, seconds):
        self._backend.sleep(seconds)


class PinnedHTTPTransport(httpx.HTTPTransport):
    """HTTP transport whose TCP connections use pre-validated, pinned addresses."""

    def __init__(self, pins: dict[str, str], network_backend=None):
        super().__init__(trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            network_backend=_PinnedNetworkBackend(pins, network_backend),
        )


class PageFetcher:
    def __init__(
        self,
        timeout: float = 15,
        max_page_chars: int = 30000,
        enabled: bool = True,
        max_retries: int = 2,
        min_text_chars: int = 200,
        browser_fetcher=None,
        http_client: httpx.Client | None = None,
        resolver=socket.getaddrinfo,
        max_download_bytes: int = 2_000_000,
        summarizer=None,
    ):
        # Client injection is a test seam only. Production requests must use the
        # owned pinned transport; MockTransport performs no network I/O.
        if http_client is not None and not isinstance(http_client._transport, httpx.MockTransport):
            raise ValueError("注入 http_client 仅支持用于测试的 httpx.MockTransport")
        if max_download_bytes <= 0:
            raise ValueError("max_download_bytes 必须大于 0")
        self.timeout = timeout
        self.max_page_chars = max_page_chars
        self.enabled = enabled
        self.max_retries = max_retries
        self.min_text_chars = min_text_chars
        self.browser_fetcher = browser_fetcher
        self.resolver = resolver
        self.max_download_bytes = max_download_bytes
        self.summarizer = summarizer
        self._owns_client = http_client is None
        self._pins: dict[str, str] = {}
        self._client = http_client or httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=PinnedHTTPTransport(self._pins),
        )

    def fetch(self, url: str, query_hint: str | None = None, *, summarize: bool = True) -> str:
        if not self.enabled:
            raise ValueError("联网抓取已禁用")
        text_limit = self.max_page_chars if summarize else max(self.max_page_chars, _FULL_CONTENT_MAX_CHARS)
        try:
            text = self._try_http_fetch(url, max_chars=text_limit)
        except (UnsafeUrlError, PageTooLargeError):
            raise
        except ValueError as exc:
            if self.browser_fetcher is not None:
                text = self.browser_fetcher.fetch(url)
            else:
                raise exc
        if len(text) < self.min_text_chars and self.browser_fetcher is not None:
            text = self.browser_fetcher.fetch(url)
        text = text[:text_limit]
        if summarize and self.summarizer is not None:
            return self.summarizer.summarize(url, text, query_hint=query_hint)
        return text

    def _try_http_fetch(self, url: str, *, max_chars: int | None = None) -> str:
        last_detail: object | None = None
        for attempt in range(self.max_retries + 1):
            headers = self._headers_for(attempt, url)
            try:
                response = self._get_following_safe_redirects(url, headers)
            except UnsafeUrlError:
                raise
            except ValueError:
                raise
            except Exception as exc:
                last_detail = exc
                continue
            if response.status_code in _RETRY_STATUS:
                last_detail = f"HTTP {response.status_code}"
                continue
            if response.status_code >= 400:
                raise ValueError(f"网页抓取失败: HTTP {response.status_code}")
            return self._extract_text(response.text)[: max_chars or self.max_page_chars]
        raise ValueError(f"网页抓取失败: {last_detail}")

    def _get_following_safe_redirects(self, url: str, headers: dict[str, str]) -> httpx.Response:
        current = url
        seen: set[str] = set()
        for redirect_count in range(_MAX_REDIRECTS + 1):
            self._validate_url(current)
            if current in seen:
                raise ValueError("网页抓取失败: 重定向循环")
            seen.add(current)
            with self._client.stream(
                "GET", current, headers=headers, follow_redirects=False
            ) as response:
                if response.status_code in _REDIRECT_STATUS:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("网页抓取失败: 重定向缺少 Location")
                    if redirect_count >= _MAX_REDIRECTS:
                        raise ValueError("网页抓取失败: 重定向过多")
                    current = urljoin(current, location)
                    continue
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = None
                    if declared_size is not None and declared_size > self.max_download_bytes:
                        raise PageTooLargeError("网页内容超过下载大小限制")
                chunks: list[bytes] = []
                downloaded = 0
                for chunk in response.iter_bytes():
                    downloaded += len(chunk)
                    if downloaded > self.max_download_bytes:
                        raise PageTooLargeError("网页内容超过下载大小限制")
                    chunks.append(chunk)
                buffered = httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=b"".join(chunks),
                )
                buffered.encoding = response.encoding
                return buffered
        raise ValueError("网页抓取失败: 重定向过多")

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

    def _validate_url(self, url: str) -> None:
        host, addresses = resolve_url(url, self.resolver)
        self._pins[host] = str(addresses[0])

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

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
