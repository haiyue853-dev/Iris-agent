from io import BytesIO
from threading import Event
from time import monotonic

import httpx
from pypdf import PdfWriter

from iris_agent.tools.builtin.web_tools import build_fetch_page_tool, build_web_extract_tool
from iris_agent.tools.execution import ToolExecutor
from iris_agent.tools.registry import ToolRegistry
from iris_agent.core.models import ToolCall
from iris_agent.web_search.extractor import PageExtractor
from iris_agent.web_search.fetcher import PageFetcher


def fetcher(handler, **kwargs):
    return PageFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                       resolver=lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))], **kwargs)


def test_extract_preserves_markdown_links_and_full_content_without_summary():
    class Summary:
        def summarize(self, *args, **kwargs):
            raise AssertionError("No extra LLM call")
    html = '<title>Title</title><nav>noise</nav><article><h1>Heading</h1><p>' + 'body ' * 100 + '</p><a href="/doc">Doc</a><ul><li>one</li></ul><pre><code>if True:\n    pass</code></pre></article>'
    page = fetcher(lambda request: httpx.Response(200, text=html), max_page_chars=10, summarizer=Summary())
    result = build_fetch_page_tool(page).invoke({"url": "https://example.com/page"})
    assert result.ok
    assert result.value["method"] == "http"
    assert result.value["title"] == "Title"
    text = result.value["text"]
    assert len(text) > 500 and "noise" not in text
    assert "# Heading" in text and "[Doc](https://example.com/doc)" in text
    assert "- one" in text and "```\nif True:\n    pass\n```" in text


def test_extract_pdf_uses_downloaded_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Title": "PDF title"})
    buffer = BytesIO()
    writer.write(buffer)
    page = fetcher(lambda request: httpx.Response(200, content=buffer.getvalue(), headers={"content-type": "application/pdf"}))
    result = page.extract("https://example.com/report.pdf")
    assert result["ok"] and result["method"] == "pdf" and result["title"] == "PDF title"


def test_batch_preserves_success_and_classifies_bad_urls_and_http_errors():
    page = fetcher(lambda request: httpx.Response(404) if request.url.path == '/missing' else httpx.Response(200, text="body"))
    tool = build_web_extract_tool(page)
    result = tool.invoke({"urls": ["https://example.com/ok", "http://127.0.0.1", "https://example.com/missing"]}).value
    assert result["successful"] == 1 and result["failed"] == 2
    assert [p.get("error_code") for p in result["pages"]] == [None, "unsafe_url", "page_http_error"]


def test_stuck_page_returns_partial_batch_and_retains_worker_slot():
    release, entered = Event(), Event()
    class SlowFetcher:
        timeout = .1
        def extract(self, url, **kwargs):
            if url == "slow":
                entered.set()
                release.wait(2)
            return {"url": url, "ok": True, "text": url}
    extractor = PageExtractor(SlowFetcher(), max_workers=2)
    try:
        started = monotonic()
        result = extractor.extract_many(["slow", "fast"])
        assert entered.is_set() and monotonic() - started < .8
        assert result["pages"][0]["error_code"] == "tool_timeout"
        assert result["pages"][1]["text"] == "fast"
        assert extractor.extract_many(["fast"])["successful"] == 1
    finally:
        release.set()


def test_browser_fallback_once_with_remaining_budget():
    class Browser:
        calls = []
        def fetch(self, url, *, timeout):
            self.calls.append(timeout)
            return "rendered"
    browser = Browser()
    page = fetcher(lambda request: httpx.Response(200, text="<html></html>"), browser_fetcher=browser, timeout=2)
    result = page.extract("https://example.com")
    assert result["method"] == "browser" and result["text"] == "rendered"
    assert len(browser.calls) == 1 and 0 < browser.calls[0] <= 2


def test_batch_tool_emits_progress_and_rejects_oversized_batches():
    page = fetcher(lambda request: httpx.Response(200, text="content"))
    registry = ToolRegistry()
    registry.register(build_web_extract_tool(page))
    assert registry.invoke("web_extract", {"urls": ["https://example.com"] * 6}).error_code == "invalid_tool_arguments"
    events = list(ToolExecutor().execute(ToolCall("id", "web_extract", {"urls": ["https://example.com"]}), registry, lambda: False))
    assert any(event.type == "tool_progress" for event in events)
    assert events[-1].data["result"]["successful"] == 1
