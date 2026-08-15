import pytest

from iris_agent.web_search.browser_fetcher import BrowserFetcher


def _fetcher(**kwargs) -> BrowserFetcher:
    return BrowserFetcher(**kwargs)


def test_fetch_returns_browser_text(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url: "浏览器渲染的正文")

    assert fetcher.fetch("https://example.com") == "浏览器渲染的正文"


def test_fetch_truncates(monkeypatch):
    fetcher = _fetcher(max_page_chars=10)
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url: "x" * 100)

    assert len(fetcher.fetch("https://example.com")) == 10


def test_fetch_rejects_private_host(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url: "x")

    with pytest.raises(ValueError):
        fetcher.fetch("http://127.0.0.1/x")


def test_fetch_rejects_non_http_scheme(monkeypatch):
    fetcher = _fetcher()
    monkeypatch.setattr(fetcher, "_fetch_via_browser", lambda url: "x")

    with pytest.raises(ValueError):
        fetcher.fetch("file:///etc/passwd")


def test_fetch_disabled_raises():
    fetcher = _fetcher(enabled=False)

    with pytest.raises(ValueError):
        fetcher.fetch("https://example.com")
