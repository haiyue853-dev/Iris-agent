"""Browser-based page fetcher (Playwright fallback for JS-heavy or anti-bot pages)."""

from __future__ import annotations

import socket
import ipaddress

from urllib.parse import urlparse

from iris_agent.web_search.fetcher import PageTooLargeError, UnsafeUrlError, resolve_url


class _DownloadBudget:
    def __init__(self, cdp, page, limit: int):
        self.cdp = cdp
        self.page = page
        self.limit = limit
        self.decoded_total = 0
        self.encoded_total = 0
        self._encoded_by_request: dict[str, float] = {}
        self._processed_events: set[tuple] = set()
        self.error: PageTooLargeError | None = None
        self.termination_failures: list[Exception] = []
        self._termination_attempted = False

    def on_data_received(self, event) -> None:
        request_id = str(event.get("requestId", ""))
        decoded = event.get("dataLength", 0) or 0
        encoded = event.get("encodedDataLength", 0) or 0
        self.decoded_total += decoded
        self.encoded_total += encoded
        self._encoded_by_request[request_id] = self._encoded_by_request.get(request_id, 0) + encoded
        self._check_limit()

    def on_loading_finished(self, event) -> None:
        request_id = str(event.get("requestId", ""))
        key = self._event_key("finished", event, event)
        if key in self._processed_events:
            return
        self._processed_events.add(key)
        reported = event.get("encodedDataLength", 0) or 0
        self._add_encoded_baseline(request_id, reported)
        self._encoded_by_request.pop(request_id, None)
        self._check_limit()

    def on_request_will_be_sent(self, event) -> None:
        response = event.get("redirectResponse")
        if not response:
            return
        key = self._event_key("redirect", event, response)
        if key in self._processed_events:
            return
        self._processed_events.add(key)
        request_id = str(event.get("requestId", ""))
        self._add_encoded_baseline(request_id, response.get("encodedDataLength", 0) or 0)
        self._encoded_by_request[request_id] = 0
        self._check_limit()

    def on_response_received(self, event) -> None:
        response = event.get("response", {})
        key = self._event_key("response", event, response)
        if key in self._processed_events:
            return
        self._processed_events.add(key)
        request_id = str(event.get("requestId", ""))
        self._add_encoded_baseline(request_id, response.get("encodedDataLength", 0) or 0)
        self._check_limit()

    def on_loading_failed(self, event) -> None:
        key = self._event_key("failed", event, event)
        if key in self._processed_events:
            return
        self._processed_events.add(key)
        request_id = str(event.get("requestId", ""))
        if "encodedDataLength" in event:
            self._add_encoded_baseline(request_id, event.get("encodedDataLength", 0) or 0)
        self._encoded_by_request.pop(request_id, None)
        self._check_limit()

    def _add_encoded_baseline(self, request_id: str, reported: float) -> None:
        counted = self._encoded_by_request.get(request_id, 0)
        self.encoded_total += max(0, reported - counted)
        self._encoded_by_request[request_id] = max(counted, reported)

    @staticmethod
    def _event_key(kind: str, event, response) -> tuple:
        return (
            kind,
            str(event.get("requestId", "")),
            event.get("timestamp"),
            response.get("url"),
            response.get("status"),
            response.get("encodedDataLength"),
        )

    def _check_limit(self) -> None:
        if max(self.decoded_total, self.encoded_total) <= self.limit:
            return
        if self.error is None:
            self.error = PageTooLargeError("浏览器页面超过下载大小限制")
        if not self._termination_attempted:
            self._terminate_download()

    def _terminate_download(self) -> None:
        self._termination_attempted = True
        operations = (
            lambda: self.cdp.send("Network.setBlockedURLs", {"urls": ["*"]}),
            lambda: self.cdp.send("Page.stopLoading"),
            self.page.close,
        )
        for operation in operations:
            try:
                operation()
            except Exception as exc:
                self.termination_failures.append(exc)
        if len(self.termination_failures) == len(operations):
            raise self.error


class BrowserFetcher:
    def __init__(
        self,
        channel: str = "msedge",
        timeout: float = 30,
        max_page_chars: int = 30000,
        enabled: bool = True,
        resolver=socket.getaddrinfo,
        max_download_bytes: int = 2_000_000,
    ):
        if max_download_bytes <= 0:
            raise ValueError("max_download_bytes 必须大于 0")
        self.channel = channel
        self.timeout = timeout
        self.max_page_chars = max_page_chars
        self.enabled = enabled
        self.resolver = resolver
        self.max_download_bytes = max_download_bytes

    def fetch(self, url: str) -> str:
        if not self.enabled:
            raise ValueError("浏览器抓取已禁用")
        host, addresses = resolve_url(url, self.resolver)
        chosen = next((address for address in addresses if address.version == 4), None)
        if chosen is None:
            raise UnsafeUrlError("浏览器抓取要求可固定的公网 IPv4 地址")
        return self._fetch_via_browser(url, host, str(chosen))[: self.max_page_chars]

    def _handle_route(
        self, route, request, blocked: list[UnsafeUrlError], expected_host: str, main_frame
    ) -> None:
        parsed = urlparse(request.url)
        hostname = parsed.hostname.lower() if parsed.hostname is not None else None
        invalid_scheme = parsed.scheme not in ("http", "https")
        dangerous_literal = False
        if hostname is not None:
            try:
                address = ipaddress.ip_address(hostname)
                dangerous_literal = not address.is_global or (
                    isinstance(address, ipaddress.IPv6Address) and address.is_site_local
                )
            except ValueError:
                pass
        cross_host = hostname != expected_host
        main_navigation = bool(getattr(request, "is_navigation_request", False)) and getattr(
            request, "frame", None
        ) == main_frame
        dangerous_request = invalid_scheme or hostname is None or dangerous_literal or cross_host
        if main_navigation and dangerous_request:
            blocked.append(UnsafeUrlError("浏览器抓取禁止危险请求或跨主机导航"))
        if dangerous_request:
            route.abort()
            return
        route.continue_()

    def _fetch_via_browser(self, url: str, navigation_host: str, navigation_ip: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel=self.channel,
                headless=True,
                args=[f"--host-resolver-rules=MAP {navigation_host} {navigation_ip}"],
            )
            context = None
            cdp = None
            primary_error = None
            result = None
            try:
                context = browser.new_context(service_workers="block")
                page = context.new_page()
                context.on("page", lambda popup: popup.close())
                cdp = context.new_cdp_session(page)
                download_budget = _DownloadBudget(cdp, page, self.max_download_bytes)
                cdp.on("Network.dataReceived", download_budget.on_data_received)
                cdp.on("Network.requestWillBeSent", download_budget.on_request_will_be_sent)
                cdp.on("Network.responseReceived", download_budget.on_response_received)
                cdp.on("Network.loadingFinished", download_budget.on_loading_finished)
                cdp.on("Network.loadingFailed", download_budget.on_loading_failed)
                cdp.send("Network.enable")
                cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                blocked: list[UnsafeUrlError] = []
                context.route(
                    "**/*",
                    lambda route, request: self._handle_route(
                        route, request, blocked, navigation_host, page.main_frame
                    ),
                )
                navigation_error = None
                try:
                    page.goto(url, timeout=int(self.timeout * 1000))
                    page.wait_for_load_state("networkidle")
                except Exception as exc:
                    navigation_error = exc
                if blocked:
                    raise blocked[0]
                if download_budget.error is not None:
                    raise download_budget.error
                if navigation_error is not None:
                    raise navigation_error
                final = urlparse(page.url)
                if final.scheme not in ("http", "https") or final.hostname is None or final.hostname.lower() != navigation_host:
                    raise UnsafeUrlError("浏览器抓取禁止访问不同主机")
                result = page.locator("body").evaluate(
                    '(el, max) => (el.innerText || "").slice(0, max)', self.max_page_chars
                )
            except BaseException as exc:
                primary_error = exc

            cleanup_errors = []
            if cdp is not None:
                try:
                    cdp.detach()
                except BaseException as exc:
                    cleanup_errors.append(exc)
            if context is not None:
                try:
                    context.close()
                except BaseException as exc:
                    cleanup_errors.append(exc)
            try:
                browser.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
            if primary_error is not None:
                raise primary_error
            if cleanup_errors:
                raise cleanup_errors[0]
            return result
