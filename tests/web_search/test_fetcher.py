import httpx
import pytest

from iris_agent.web_search.fetcher import PageFetcher

PAGE_HTML = """
<html><head>
<style>.x{color:red}</style>
<script>var secret=1;</script>
</head><body>
<nav>导航栏</nav>
<h1>页面标题</h1>
<p>正文第一段内容。</p>
<p>正文第二段内容。</p>
<footer>页脚</footer>
</body></html>
"""


def _fetcher(html: str, **kwargs) -> PageFetcher:
    def handler(request):
        return httpx.Response(200, text=html)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    defaults = dict(http_client=http)
    defaults.update(kwargs)
    return PageFetcher(**defaults)


def test_fetch_extracts_text_without_noise():
    fetcher = _fetcher(PAGE_HTML)

    text = fetcher.fetch("https://example.com/page")

    assert "正文第一段" in text
    assert "正文第二段" in text
    assert "导航栏" not in text
    assert "页脚" not in text
    assert "var secret" not in text


def test_fetch_truncates_text():
    fetcher = _fetcher(PAGE_HTML, max_page_chars=10)

    text = fetcher.fetch("https://example.com/page")

    assert len(text) <= 10


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"])
def test_fetch_rejects_non_http_scheme(url):
    fetcher = _fetcher(PAGE_HTML)

    with pytest.raises(ValueError):
        fetcher.fetch(url)


@pytest.mark.parametrize("url", [
    "http://localhost:8000/x",
    "http://127.0.0.1/x",
    "http://192.168.1.1/x",
    "http://10.0.0.1/x",
    "http://172.16.0.1/x",
    "http://169.254.169.254/latest/meta-data",
])
def test_fetch_rejects_private_or_loopback(url):
    fetcher = _fetcher(PAGE_HTML)

    with pytest.raises(ValueError):
        fetcher.fetch(url)


def test_fetch_allows_public_host():
    fetcher = _fetcher(PAGE_HTML)

    text = fetcher.fetch("https://example.com/page")

    assert "正文第一段" in text


def test_fetch_returns_error_on_network_failure():
    def handler(request):
        raise httpx.ConnectError("boom")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PageFetcher(http_client=http)

    with pytest.raises(ValueError):
        fetcher.fetch("https://example.com/page")


def test_fetch_disabled_raises():
    fetcher = _fetcher(PAGE_HTML, enabled=False)

    with pytest.raises(ValueError):
        fetcher.fetch("https://example.com/page")
