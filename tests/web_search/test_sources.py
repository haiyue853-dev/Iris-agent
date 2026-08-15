import httpx

from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource

BING_HTML = """
<html><body>
<ol id="b_results">
<li class="b_algo">
  <h2><a href="https://example.com/a">结果 A</a></h2>
  <p>摘要 A</p>
</li>
<li class="b_algo">
  <h2><a href="https://example.com/b">结果 B</a></h2>
  <p>摘要 B</p>
</li>
</ol>
</body></html>
"""

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://example.com/a">结果 A</a>
  <a class="result__snippet">摘要 A</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/b">结果 B</a>
  <a class="result__snippet">摘要 B</a>
</div>
</body></html>
"""


def _client(html: str) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html)))


def test_bing_source_parses_results():
    source = BingSearchSource(http_client=_client(BING_HTML))

    results = source.search("查询", 5)

    assert [r.title for r in results] == ["结果 A", "结果 B"]
    assert results[0].url == "https://example.com/a"
    assert results[0].snippet == "摘要 A"


def test_bing_source_respects_limit():
    source = BingSearchSource(http_client=_client(BING_HTML))

    results = source.search("查询", 1)

    assert len(results) == 1


def test_duckduckgo_source_parses_results():
    source = DuckDuckGoSearchSource(http_client=_client(DDG_HTML))

    results = source.search("查询", 5)

    assert [r.title for r in results] == ["结果 A", "结果 B"]
    assert results[0].url == "https://example.com/a"
    assert results[0].snippet == "摘要 A"


def test_duckduckgo_source_returns_empty_on_error():
    def handler(request):
        raise httpx.ConnectError("boom")
    source = DuckDuckGoSearchSource(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert source.search("查询", 5) == []
