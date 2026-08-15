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


def _fetcher_with_sequence(responses) -> PageFetcher:
    def handler(request):
        return responses.pop(0)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return PageFetcher(http_client=http, max_retries=2)


def test_fetch_retries_on_antibot_status():
    fetcher = _fetcher_with_sequence([
        httpx.Response(521, text="antibot"),
        httpx.Response(200, text=PAGE_HTML),
    ])

    text = fetcher.fetch("https://example.com/page")

    assert "正文第一段" in text


def test_fetch_switches_user_agent_on_retry():
    seen_agents = []
    def handler(request):
        seen_agents.append(request.headers.get("User-Agent", ""))
        return responses.pop(0)
    responses = [
        httpx.Response(521, text="antibot"),
        httpx.Response(200, text=PAGE_HTML),
    ]
    http = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PageFetcher(http_client=http, max_retries=2)

    fetcher.fetch("https://example.com/page")

    assert len(seen_agents) == 2
    assert seen_agents[0] != seen_agents[1]


def test_fetch_raises_after_retries_exhausted():
    fetcher = _fetcher_with_sequence([
        httpx.Response(521, text="antibot"),
        httpx.Response(521, text="antibot"),
        httpx.Response(521, text="antibot"),
    ])

    with pytest.raises(ValueError) as exc:
        fetcher.fetch("https://example.com/page")

    assert "521" in str(exc.value)


def test_fetch_does_not_retry_on_404():
    responses = [httpx.Response(404, text="not found")]
    fetcher = _fetcher_with_sequence(responses)

    with pytest.raises(ValueError) as exc:
        fetcher.fetch("https://example.com/page")

    assert "404" in str(exc.value)
