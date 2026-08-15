import httpx

from iris_agent.web_search.models import SearchResult
from iris_agent.web_search.search import WebSearchClient
from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource

BING_HTML = """
<html><body>
<ol id="b_results">
<li class="b_algo">
  <h2><a href="https://example.com/a">Agent 面试经验 A</a></h2>
  <p>这是结果 A 的摘要，讲面试经验。</p>
</li>
<li class="b_algo">
  <h2><a href="https://example.com/b">Agent 面试经验 B</a></h2>
  <p>这是结果 B 的摘要。</p>
</li>
<li class="b_algo">
  <h2><a href="https://example.com/c">Agent 面试经验 C</a></h2>
  <p>这是结果 C 的摘要。</p>
</li>
</ol>
</body></html>
"""

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://example.com/x">DDG 结果 X</a>
  <a class="result__snippet">摘要 X</a>
</div>
</body></html>
"""


def _client(html: str, **kwargs) -> WebSearchClient:
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html)))
    source = BingSearchSource(http_client=http)
    defaults = dict(sources=[source])
    defaults.update(kwargs)
    return WebSearchClient(**defaults)


def test_search_parses_results():
    client = _client(BING_HTML)

    results = client.search("agent 面试经验")

    assert len(results) == 3
    assert results[0].title == "Agent 面试经验 A"
    assert results[0].url == "https://example.com/a"
    assert "摘要" in results[0].snippet


def test_search_respects_limit():
    client = _client(BING_HTML)

    results = client.search("agent 面试经验", limit=2)

    assert len(results) == 2


def test_search_truncates_snippet():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=BING_HTML)))
    source = BingSearchSource(http_client=http, max_snippet_chars=5)
    client = WebSearchClient(sources=[source])

    results = client.search("agent 面试经验")

    assert len(results[0].snippet) <= 5


def test_search_returns_empty_when_no_algo():
    client = _client("<html><body>没有结果</body></html>")

    assert client.search("无关词") == []


def test_search_returns_empty_on_http_error():
    def handler(request):
        raise httpx.ConnectError("boom")
    source = BingSearchSource(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = WebSearchClient(sources=[source])

    assert client.search("查询") == []


def test_search_returns_empty_when_disabled():
    client = _client(BING_HTML, enabled=False)

    assert client.search("查询") == []


def test_search_result_to_dict():
    result = SearchResult(title="标题", url="https://x.com", snippet="摘要")

    assert result.to_dict() == {"title": "标题", "url": "https://x.com", "snippet": "摘要"}


def test_search_falls_back_to_second_source():
    def empty_handler(request):
        return httpx.Response(200, text="<html>无结果</html>")
    empty_source = BingSearchSource(http_client=httpx.Client(transport=httpx.MockTransport(empty_handler)))
    ddg_source = DuckDuckGoSearchSource(http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=DDG_HTML))))
    client = WebSearchClient(sources=[empty_source, ddg_source])

    results = client.search("查询")

    assert len(results) == 1
    assert results[0].title == "DDG 结果 X"


def test_search_records_error_when_all_sources_empty():
    def empty_handler(request):
        return httpx.Response(200, text="<html>无结果</html>")
    source = BingSearchSource(http_client=httpx.Client(transport=httpx.MockTransport(empty_handler)))
    client = WebSearchClient(sources=[source])

    assert client.search("查询") == []
    assert client.last_error is not None
