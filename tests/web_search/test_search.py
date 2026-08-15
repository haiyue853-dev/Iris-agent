import httpx

from iris_agent.web_search.models import SearchResult
from iris_agent.web_search.search import WebSearchClient

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


def _client(html: str, **kwargs) -> WebSearchClient:
    def handler(request):
        return httpx.Response(200, text=html)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    defaults = dict(http_client=http)
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
    client = _client(BING_HTML, max_snippet_chars=5)

    results = client.search("agent 面试经验")

    assert len(results[0].snippet) <= 5


def test_search_returns_empty_when_no_algo():
    client = _client("<html><body>没有结果</body></html>")

    assert client.search("无关词") == []


def test_search_returns_empty_on_http_error():
    def handler(request):
        raise httpx.ConnectError("boom")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WebSearchClient(http_client=http)

    assert client.search("查询") == []


def test_search_returns_empty_when_disabled():
    client = _client(BING_HTML, enabled=False)

    assert client.search("查询") == []


def test_search_result_to_dict():
    result = SearchResult(title="标题", url="https://x.com", snippet="摘要")

    assert result.to_dict() == {"title": "标题", "url": "https://x.com", "snippet": "摘要"}
