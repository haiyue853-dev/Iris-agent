"""Browser-based page fetcher (Playwright fallback for JS-heavy or anti-bot pages)."""

from __future__ import annotations

from iris_agent.web_search.fetcher import PageFetcher


class BrowserFetcher:
    def __init__(
        self,
        channel: str = "msedge",
        timeout: float = 30,
        max_page_chars: int = 30000,
        enabled: bool = True,
    ):
        self.channel = channel
        self.timeout = timeout
        self.max_page_chars = max_page_chars
        self.enabled = enabled

    def fetch(self, url: str) -> str:
        if not self.enabled:
            raise ValueError("浏览器抓取已禁用")
        PageFetcher._validate_url(url)
        return self._fetch_via_browser(url)[: self.max_page_chars]

    def _fetch_via_browser(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel=self.channel, headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=int(self.timeout * 1000))
                page.wait_for_load_state("networkidle")
                return page.inner_text("body")
            finally:
                browser.close()
