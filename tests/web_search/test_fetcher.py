import httpx
import httpcore
import pytest

from iris_agent.web_search.fetcher import PageFetcher, PageTooLargeError, PinnedHTTPTransport, UnsafeUrlError


def public_resolver(host, *args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def resolver_for(*addresses):
    return lambda host, *args, **kwargs: [
        (2, 1, 6, "", (address, 0)) for address in addresses
    ]

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
    defaults = dict(http_client=http, resolver=public_resolver)
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
    fetcher = _fetcher(PAGE_HTML, resolver=public_resolver)

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
    fetcher = PageFetcher(http_client=http, resolver=public_resolver)

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
    return PageFetcher(http_client=http, max_retries=2, resolver=public_resolver)


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
    fetcher = PageFetcher(http_client=http, max_retries=2, resolver=public_resolver)

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


class FakeBrowserFetcher:
    def __init__(self, text: str):
        self.text = text
        self.called = False

    def fetch(self, url):
        self.called = True
        return self.text


def test_fetch_falls_back_to_browser_on_failure():
    browser = FakeBrowserFetcher("浏览器渲染的正文")
    fetcher = _fetcher_with_sequence([
        httpx.Response(521, text="antibot"),
        httpx.Response(521, text="antibot"),
        httpx.Response(521, text="antibot"),
    ])
    fetcher.browser_fetcher = browser

    text = fetcher.fetch("https://example.com/page")

    assert text == "浏览器渲染的正文"
    assert browser.called is True


def test_fetch_falls_back_to_browser_on_empty_shell():
    browser = FakeBrowserFetcher("浏览器渲染的正文")
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="<html><body><div id=app></div></body></html>")))
    fetcher = PageFetcher(http_client=http, browser_fetcher=browser, min_text_chars=50, resolver=public_resolver)

    text = fetcher.fetch("https://example.com/page")

    assert text == "浏览器渲染的正文"
    assert browser.called is True


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.2", "169.254.169.254", "fd00::1"])
def test_fetch_rejects_domain_resolving_to_non_public_address(address):
    fetcher = _fetcher(PAGE_HTML, resolver=resolver_for(address))

    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://attacker.example/page")


@pytest.mark.parametrize("address", ["100.64.0.1", "100.127.255.254", "fec0::1", "192.0.2.1"])
def test_fetch_rejects_every_non_global_address(address):
    fetcher = _fetcher(PAGE_HTML, resolver=resolver_for(address))
    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://attacker.example/page")


def test_fetch_rejects_domain_if_any_dns_result_is_non_public():
    fetcher = _fetcher(PAGE_HTML, resolver=resolver_for("93.184.216.34", "10.0.0.2"))

    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://mixed.example/page")


def test_fetch_rejects_dns_failure():
    def failing_resolver(*args, **kwargs):
        raise OSError("dns unavailable")

    with pytest.raises(UnsafeUrlError, match="DNS"):
        _fetcher(PAGE_HTML, resolver=failing_resolver).fetch("https://example.com")


def test_redirect_to_literal_private_ip_is_rejected_before_second_request():
    requested = []
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PageFetcher(http_client=http, resolver=public_resolver)

    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://example.com/start")

    assert requested == ["https://example.com/start"]


def test_redirect_to_domain_resolving_private_is_rejected():
    def resolver(host, *args, **kwargs):
        return resolver_for("10.0.0.2" if host == "private.example" else "93.184.216.34")(host)
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "https://private.example/secret"})
    ))

    with pytest.raises(UnsafeUrlError):
        PageFetcher(http_client=http, resolver=resolver).fetch("https://public.example/start")


def test_safe_relative_redirect_chain_succeeds():
    requested = []
    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/middle"})
        if request.url.path == "/middle":
            return httpx.Response(307, headers={"Location": "https://other.example/end"})
        return httpx.Response(200, text=PAGE_HTML)
    fetcher = PageFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)), resolver=public_resolver)

    assert "正文第一段" in fetcher.fetch("https://example.com/start")
    assert requested == ["https://example.com/start", "https://example.com/middle", "https://other.example/end"]


def test_redirect_loop_fails_clearly():
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "/start"})
    ))
    with pytest.raises(ValueError, match="循环"):
        PageFetcher(http_client=http, resolver=public_resolver).fetch("https://example.com/start")


def test_redirect_limit_fails_clearly():
    def handler(request):
        number = int(request.url.path.removeprefix("/"))
        return httpx.Response(302, headers={"Location": f"/{number + 1}"})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="过多"):
        PageFetcher(http_client=http, resolver=public_resolver).fetch("https://example.com/0")


def test_redirect_without_location_fails_clearly():
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(302)))
    with pytest.raises(ValueError, match="Location"):
        PageFetcher(http_client=http, resolver=public_resolver).fetch("https://example.com/start")


def test_unsafe_redirect_never_falls_back_to_browser():
    browser = FakeBrowserFetcher("must not be returned")
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
    ))
    with pytest.raises(UnsafeUrlError):
        PageFetcher(http_client=http, browser_fetcher=browser, resolver=public_resolver).fetch("https://example.com")
    assert browser.called is False


def test_close_only_closes_owned_client():
    injected = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=PAGE_HTML)))
    PageFetcher(http_client=injected, resolver=public_resolver).close()
    assert injected.is_closed is False

    owned = PageFetcher(resolver=public_resolver)
    owned.close()
    assert owned._client.is_closed is True


def test_rejects_injected_client_that_can_bypass_pinned_transport():
    client = httpx.Client()
    try:
        with pytest.raises(ValueError, match="MockTransport"):
            PageFetcher(http_client=client, resolver=public_resolver)
    finally:
        client.close()


def test_pinned_transport_connects_to_validated_ip_and_preserves_tls_sni():
    class Stream(httpcore.MockStream):
        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            backend.sni = server_hostname
            return self
    class Backend(httpcore.NetworkBackend):
        connected_host = None
        sni = None
        def connect_tcp(self, host, port, **kwargs):
            self.connected_host = host
            return Stream([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])
        def connect_unix_socket(self, *args, **kwargs): raise AssertionError
    backend = Backend()
    pins = {"example.com": "93.184.216.34"}
    client = httpx.Client(transport=PinnedHTTPTransport(pins, network_backend=backend))

    response = client.get("https://example.com/")

    assert response.text == "ok"
    assert backend.connected_host == "93.184.216.34"
    assert backend.sni == "example.com"


def test_owned_fetcher_resolves_once_and_pins_before_request():
    calls = []
    def resolver(host, *args, **kwargs):
        calls.append(host)
        return public_resolver(host)
    fetcher = PageFetcher(resolver=resolver)
    captured = {}
    def fake_stream(method, url, **kwargs):
        captured.update(fetcher._pins)
        mock = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=PAGE_HTML)))
        return mock.stream(method, url, **kwargs)
    fetcher._client.stream = fake_stream

    fetcher.fetch("https://example.com/page")

    assert calls == ["example.com"]
    assert captured == {"example.com": "93.184.216.34"}


class TrackingStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.read_count = 0
        self.closed = False
    def __iter__(self):
        for chunk in self.chunks:
            self.read_count += 1
            yield chunk
    def close(self): self.closed = True


def test_content_length_over_limit_is_rejected_without_reading_and_closed():
    stream = TrackingStream([b"never read"])
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Length": "11"}, stream=stream)
    ))
    fetcher = PageFetcher(http_client=http, resolver=public_resolver, max_download_bytes=10)

    with pytest.raises(PageTooLargeError):
        fetcher.fetch("https://example.com")

    assert stream.read_count == 0
    assert stream.closed is True


def test_stream_without_length_is_stopped_when_accumulated_limit_exceeded():
    stream = TrackingStream([b"12345", b"67890", b"x", b"not-read"])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)))
    fetcher = PageFetcher(http_client=http, resolver=public_resolver, max_download_bytes=10)

    with pytest.raises(PageTooLargeError):
        fetcher.fetch("https://example.com")

    assert stream.read_count == 3
    assert stream.closed is True


def test_download_exactly_at_limit_succeeds_and_closes_response():
    stream = TrackingStream([b"<p>1234</p>"])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)))
    size = len(b"<p>1234</p>")
    fetcher = PageFetcher(http_client=http, resolver=public_resolver, max_download_bytes=size)

    assert fetcher.fetch("https://example.com") == "1234"
    assert stream.closed is True


def test_invalid_download_limit_is_rejected():
    with pytest.raises(ValueError, match="max_download_bytes"):
        PageFetcher(resolver=public_resolver, max_download_bytes=0)


def test_page_too_large_never_falls_back_to_browser():
    browser = FakeBrowserFetcher("must not be returned")
    http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Length": "100"}, content=b"")
    ))
    with pytest.raises(PageTooLargeError):
        PageFetcher(
            http_client=http, resolver=public_resolver, browser_fetcher=browser, max_download_bytes=10
        ).fetch("https://example.com")
    assert browser.called is False
