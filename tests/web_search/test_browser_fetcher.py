import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from iris_agent.web_search.browser_fetcher import BrowserFetcher, _DownloadBudget
from iris_agent.web_search.fetcher import PageFetcher, PageTooLargeError, UnsafeUrlError


def public_resolver(host, *args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def _fetcher(**kwargs) -> BrowserFetcher:
    kwargs.setdefault("resolver", public_resolver)
    return BrowserFetcher(**kwargs)


def test_fetch_returns_browser_text(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url, host, ip: "浏览器渲染的正文")

    assert fetcher.fetch("https://example.com") == "浏览器渲染的正文"


def test_fetch_truncates(monkeypatch):
    fetcher = _fetcher(max_page_chars=10)
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url, host, ip: "x" * 100)

    assert len(fetcher.fetch("https://example.com")) == 10


def test_fetch_rejects_private_host(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url, host, ip: "x")

    with pytest.raises(ValueError):
        fetcher.fetch("http://127.0.0.1/x")


def test_fetch_rejects_non_http_scheme(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url, host, ip: "x")

    with pytest.raises(ValueError):
        fetcher.fetch("file:///etc/passwd")


def test_fetch_disabled_raises():
    fetcher = _fetcher(enabled=False)

    with pytest.raises(ValueError):
        fetcher.fetch("https://example.com")


def test_invalid_download_limit_is_rejected():
    with pytest.raises(ValueError, match="max_download_bytes"):
        _fetcher(max_download_bytes=0)


class FakeCDP:
    def __init__(self):
        self.handlers = {}
        self.sent = []
    def on(self, event, handler): self.handlers[event] = handler
    def send(self, method, params=None): self.sent.append((method, params))
    def detach(self): pass


def test_download_budget_termination_continues_after_page_close_failure():
    class CDP(FakeCDP):
        pass
    class Page:
        def close(self): raise RuntimeError("close failed")
    cdp = CDP()
    budget = _DownloadBudget(cdp, Page(), 10)

    budget.on_data_received({"requestId": "1", "dataLength": 11, "encodedDataLength": 5})
    budget.on_data_received({"requestId": "1", "dataLength": 2, "encodedDataLength": 1})

    assert budget.decoded_total == 13
    assert budget.encoded_total == 6
    assert cdp.sent.count(("Network.setBlockedURLs", {"urls": ["*"]})) == 1
    assert cdp.sent.count(("Page.stopLoading", None)) == 1
    assert isinstance(budget.error, PageTooLargeError)


def test_download_budget_loading_finished_adds_only_encoded_difference():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 100)
    budget.on_data_received({"requestId": "a", "dataLength": 4, "encodedDataLength": 3})
    budget.on_loading_finished({"requestId": "a", "encodedDataLength": 10})
    budget.on_loading_finished({"requestId": "a", "encodedDataLength": 10})
    budget.on_loading_finished({"requestId": "b", "encodedDataLength": 7})

    assert budget.decoded_total == 4
    assert budget.encoded_total == 17


def test_encoded_only_budget_can_exceed_limit():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 10)
    budget.on_data_received({"requestId": "a", "dataLength": 0, "encodedDataLength": 11})
    assert isinstance(budget.error, PageTooLargeError)


def test_all_download_termination_layers_failing_still_raises_page_too_large():
    class CDP(FakeCDP):
        def send(self, method, params=None): raise RuntimeError(method)
    class Page:
        def close(self): raise RuntimeError("close")
    budget = _DownloadBudget(CDP(), Page(), 1)
    with pytest.raises(PageTooLargeError):
        budget.on_data_received({"requestId": "a", "dataLength": 2})
    assert len(budget.termination_failures) == 3


def test_same_request_id_redirect_hops_and_final_response_share_budget():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 20)
    budget.on_data_received({"requestId": "a", "dataLength": 2, "encodedDataLength": 3})
    budget.on_request_will_be_sent({
        "requestId": "a", "timestamp": 1, "redirectResponse": {"url": "https://example.com/a", "encodedDataLength": 10}
    })
    budget.on_request_will_be_sent({
        "requestId": "a", "timestamp": 2, "redirectResponse": {"url": "https://example.com/b", "encodedDataLength": 9}
    })
    budget.on_data_received({"requestId": "a", "dataLength": 4, "encodedDataLength": 1})
    budget.on_loading_finished({"requestId": "a", "timestamp": 3, "encodedDataLength": 5})

    assert budget.encoded_total == 24
    assert isinstance(budget.error, PageTooLargeError)


def test_response_received_encoded_baseline_can_exceed_budget():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 10)
    event = {
        "requestId": "a", "timestamp": 1,
        "response": {"url": "https://example.com", "status": 200, "encodedDataLength": 11},
    }
    budget.on_response_received(event)
    budget.on_response_received(event)
    assert budget.encoded_total == 11
    assert isinstance(budget.error, PageTooLargeError)


def test_loading_failed_keeps_data_and_adds_only_available_encoded_difference():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 100)
    budget.on_data_received({"requestId": "a", "dataLength": 7, "encodedDataLength": 4})
    failed = {"requestId": "a", "timestamp": 2, "encodedDataLength": 9}
    budget.on_loading_failed(failed)
    budget.on_loading_failed(failed)
    assert budget.decoded_total == 7
    assert budget.encoded_total == 9


def test_loading_finished_duplicate_after_state_cleanup_is_idempotent():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 100)
    finished = {"requestId": "a", "timestamp": 3, "encodedDataLength": 8}
    budget.on_loading_finished(finished)
    budget.on_loading_finished(finished)
    assert budget.encoded_total == 8


def test_identical_data_received_events_are_distinct_increments():
    budget = _DownloadBudget(FakeCDP(), type("Page", (), {"close": lambda self: None})(), 12)
    event = {"requestId": "a", "timestamp": 4, "dataLength": 7, "encodedDataLength": 5}
    budget.on_data_received(event)
    budget.on_data_received(event)
    budget.on_loading_finished({"requestId": "a", "timestamp": 5, "encodedDataLength": 10})
    assert budget.decoded_total == 14
    assert budget.encoded_total == 10
    assert isinstance(budget.error, PageTooLargeError)


class TextLocator:
    def __init__(self, text): self.text = text
    def evaluate(self, expression, arg): return self.text[:arg]


class FakeRequest:
    def __init__(self, url, *, navigation=False, frame=None):
        self.url = url
        self.is_navigation_request = navigation
        self.frame = frame


class FakeRoute:
    def __init__(self): self.action = None
    def continue_(self): self.action = "continue"
    def abort(self): self.action = "abort"


def test_route_handler_allows_same_host_subresource():
    fetcher = _fetcher()
    route = FakeRoute()
    blocked = []
    main_frame = object()
    fetcher._handle_route(route, FakeRequest("https://example.com/app.js"), blocked, "example.com", main_frame)
    assert route.action == "continue"
    assert blocked == []


def test_route_handler_aborts_private_subresource_without_blocking_page():
    fetcher = _fetcher()
    route = FakeRoute()
    blocked = []
    fetcher._handle_route(route, FakeRequest("http://127.0.0.1/secret"), blocked, "example.com", object())
    assert route.action == "abort"
    assert blocked == []


def test_cross_host_subresource_is_aborted_without_failing_page():
    fetcher = _fetcher()
    route = FakeRoute()
    blocked = []
    main_frame = object()
    fetcher._handle_route(
        route, FakeRequest("https://cdn.example/app.js", frame=main_frame), blocked, "example.com", main_frame
    )
    assert route.action == "abort"
    assert blocked == []


@pytest.mark.parametrize("url", [
    "https://evil.example/redirect",
    "http://127.0.0.1/secret",
    "file:///etc/passwd",
])
def test_dangerous_main_navigation_is_aborted_and_fails_page(url):
    fetcher = _fetcher()
    route = FakeRoute()
    blocked = []
    main_frame = object()
    fetcher._handle_route(
        route,
        FakeRequest(url, navigation=True, frame=main_frame),
        blocked,
        "example.com",
        main_frame,
    )
    assert route.action == "abort"
    assert isinstance(blocked[0], UnsafeUrlError)


def test_browser_rejects_final_private_url_and_closes(monkeypatch):
    events = {"closed": False, "routed": False, "service_workers": None, "args": None}
    class Page:
        url = "http://127.0.0.1/final"
        def goto(self, url, timeout): pass
        def wait_for_load_state(self, state): pass
        def inner_text(self, selector): return "unsafe"
    class Browser:
        def new_context(self, **kwargs):
            events["service_workers"] = kwargs.get("service_workers")
            class Context:
                def route(self, pattern, handler): events["routed"] = pattern == "**/*"
                def new_page(self): return Page()
                def on(self, event, handler): pass
                def new_cdp_session(self, page): return FakeCDP()
                def close(self): pass
            return Context()
        def close(self):
            events["closed"] = True
            raise RuntimeError("browser close failed")
    class Chromium:
        def launch(self, **kwargs):
            events["args"] = kwargs.get("args")
            return Browser()
    class Playwright:
        chromium = Chromium()
    class Manager:
        def __enter__(self): return Playwright()
        def __exit__(self, *args): pass
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: Manager())

    with pytest.raises(UnsafeUrlError):
        _fetcher().fetch("https://example.com")
    assert events["closed"] is True
    assert events["routed"] is True
    assert events["service_workers"] == "block"
    assert events["args"] == ["--host-resolver-rules=MAP example.com 93.184.216.34"]


def test_context_route_handler_is_triggered_and_blocks_cross_host(monkeypatch):
    events = {"action": None, "closed": False}
    class Route:
        def continue_(self): events["action"] = "continue"
        def abort(self): events["action"] = "abort"
    class Page:
        url = "https://example.com/"
        main_frame = object()
        def goto(self, url, timeout):
            context.handler(
                Route(), FakeRequest("https://evil.example/redirect", navigation=True, frame=self.main_frame)
            )
        def wait_for_load_state(self, state): pass
        def inner_text(self, selector): return "unsafe"
    class Context:
        def route(self, pattern, handler): self.handler = handler
        def new_page(self): return Page()
        def on(self, event, handler): pass
        def new_cdp_session(self, page): return FakeCDP()
        def close(self): pass
    context = Context()
    class Browser:
        def new_context(self, **kwargs): return context
        def close(self): events["closed"] = True
    class Manager:
        def __enter__(self):
            class Chromium:
                def launch(self, **kwargs): return Browser()
            class P: chromium = Chromium()
            return P()
        def __exit__(self, *args): pass
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: Manager())

    with pytest.raises(UnsafeUrlError, match="主机"):
        _fetcher().fetch("https://example.com")
    assert events == {"action": "abort", "closed": True}


@pytest.mark.parametrize("subresource_url", [
    "https://cdn.example/app.js",
    "http://127.0.0.1/secret",
    "file:///etc/passwd",
])
def test_dangerous_subresource_abort_still_returns_main_document(monkeypatch, subresource_url):
    events = {"action": None}
    class Route:
        def continue_(self): events["action"] = "continue"
        def abort(self): events["action"] = "abort"
    class Page:
        url = "https://example.com/"
        main_frame = object()
        def goto(self, url, timeout):
            context.handler(Route(), FakeRequest(subresource_url, frame=self.main_frame))
        def wait_for_load_state(self, state): pass
        def locator(self, selector): return TextLocator("main body")
    class Context:
        def route(self, pattern, handler): self.handler = handler
        def new_page(self): return Page()
        def on(self, event, handler): pass
        def new_cdp_session(self, page): return FakeCDP()
        def close(self): pass
    context = Context()
    class Browser:
        def new_context(self, **kwargs): return context
        def close(self): pass
    class Manager:
        def __enter__(self):
            class Chromium:
                def launch(self, **kwargs): return Browser()
            class P: chromium = Chromium()
            return P()
        def __exit__(self, *args): pass
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: Manager())

    assert _fetcher().fetch("https://example.com") == "main body"
    assert events["action"] == "abort"


def test_browser_closes_popup_pages(monkeypatch):
    events = {"popup_closed": False}
    class Popup:
        def close(self): events["popup_closed"] = True
    class Page:
        url = "https://example.com/"
        def goto(self, url, timeout): context.page_handler(Popup())
        def wait_for_load_state(self, state): pass
        def locator(self, selector): return TextLocator("safe")
    class Context:
        def route(self, pattern, handler): pass
        def new_page(self): return Page()
        def on(self, event, handler): self.page_handler = handler
        def new_cdp_session(self, page): return FakeCDP()
        def close(self): pass
    context = Context()
    class Browser:
        def new_context(self, **kwargs): return context
        def close(self): pass
    class Manager:
        def __enter__(self):
            class Chromium:
                def launch(self, **kwargs): return Browser()
            class P: chromium = Chromium()
            return P()
        def __exit__(self, *args): pass
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: Manager())

    assert _fetcher().fetch("https://example.com") == "safe"
    assert events["popup_closed"] is True


def test_concurrent_fetches_keep_host_and_ip_request_local(monkeypatch):
    barrier = Barrier(2)
    seen = []
    def resolver(host, *args, **kwargs):
        address = "93.184.216.34" if host == "one.example" else "8.8.8.8"
        return [(2, 1, 6, "", (address, 0))]
    fetcher = BrowserFetcher(resolver=resolver)
    def fake_browser(url, host, ip):
        barrier.wait(timeout=2)
        seen.append((url, host, ip))
        return host
    monkeypatch.setattr(fetcher, "_fetch_via_browser", fake_browser)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetcher.fetch, ["https://one.example/a", "https://two.example/b"]))

    assert results == ["one.example", "two.example"]
    assert set(seen) == {
        ("https://one.example/a", "one.example", "93.184.216.34"),
        ("https://two.example/b", "two.example", "8.8.8.8"),
    }


def _run_cdp_fetch(
    monkeypatch, data_lengths, *, limit, body="main body", max_chars=30000,
    cdp_setup_error=None, browser_close_error=None,
):
    events = {"page_closed": False, "evaluate": None, "context_closed": False, "browser_closed": False}
    cdp = FakeCDP()
    class Locator:
        def evaluate(self, expression, arg):
            events["evaluate"] = (expression, arg)
            return body[:arg]
    class Page:
        url = "https://example.com/"
        main_frame = object()
        def goto(self, url, timeout):
            for length in data_lengths:
                cdp.handlers["Network.dataReceived"]({"requestId": "1", "dataLength": length})
        def wait_for_load_state(self, state): pass
        def locator(self, selector):
            assert selector == "body"
            return Locator()
        def close(self): events["page_closed"] = True
    class Context:
        def route(self, pattern, handler): pass
        def new_page(self): return Page()
        def on(self, event, handler): pass
        def new_cdp_session(self, page):
            if cdp_setup_error: raise cdp_setup_error
            return cdp
        def close(self): events["context_closed"] = True
    class Browser:
        def new_context(self, **kwargs): return Context()
        def close(self):
            events["browser_closed"] = True
            if browser_close_error: raise browser_close_error
    class Manager:
        def __enter__(self):
            class Chromium:
                def launch(self, **kwargs): return Browser()
            class P: chromium = Chromium()
            return P()
        def __exit__(self, *args): pass
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: Manager())
    fetcher = _fetcher(max_download_bytes=limit, max_page_chars=max_chars)
    return fetcher, cdp, events


def test_cdp_download_budget_exceeded_closes_page_and_raises(monkeypatch):
    fetcher, cdp, events = _run_cdp_fetch(monkeypatch, [6, 5], limit=10)
    with pytest.raises(PageTooLargeError):
        fetcher.fetch("https://example.com")
    assert events["page_closed"] is True
    assert ("Network.enable", None) in cdp.sent
    assert ("Network.setCacheDisabled", {"cacheDisabled": True}) in cdp.sent


def test_cdp_setup_failure_fails_closed_and_cleans_up(monkeypatch):
    setup_error = RuntimeError("CDP unavailable")
    fetcher, _, events = _run_cdp_fetch(
        monkeypatch, [], limit=10, cdp_setup_error=setup_error
    )
    with pytest.raises(RuntimeError, match="CDP unavailable"):
        fetcher.fetch("https://example.com")
    assert events["context_closed"] is True
    assert events["browser_closed"] is True


def test_cleanup_error_does_not_override_page_too_large(monkeypatch):
    fetcher, _, _ = _run_cdp_fetch(
        monkeypatch, [11], limit=10, browser_close_error=RuntimeError("browser close")
    )
    with pytest.raises(PageTooLargeError):
        fetcher.fetch("https://example.com")


def test_cdp_download_budget_exact_boundary_succeeds(monkeypatch):
    fetcher, _, events = _run_cdp_fetch(monkeypatch, [6, 4], limit=10)
    assert fetcher.fetch("https://example.com") == "main body"
    assert events["page_closed"] is False


def test_browser_extracts_and_truncates_text_inside_page(monkeypatch):
    fetcher, _, events = _run_cdp_fetch(monkeypatch, [], limit=100, body="x" * 100, max_chars=7)
    assert fetcher.fetch("https://example.com") == "x" * 7
    expression, arg = events["evaluate"]
    assert "slice(0, max)" in expression
    assert arg == 7


def test_short_http_fallback_uses_browser_with_same_download_budget(monkeypatch):
    browser = _fetcher(max_download_bytes=123)
    monkeypatch.setattr(browser, "_fetch_via_browser", lambda url, host, ip: "browser body")
    import httpx
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="short")))
    fetcher = PageFetcher(
        http_client=http,
        resolver=public_resolver,
        browser_fetcher=browser,
        min_text_chars=10,
        max_download_bytes=123,
    )
    assert fetcher.fetch("https://example.com") == "browser body"
    assert browser.max_download_bytes == fetcher.max_download_bytes == 123
