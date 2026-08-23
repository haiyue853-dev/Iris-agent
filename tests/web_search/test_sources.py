import httpx
import pytest

from iris_agent.web_search.models import SearchOptions
from iris_agent.web_search.sources import BingSearchSource, DuckDuckGoSearchSource, TavilySearchSource

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


def test_tavily_source_maps_complete_options_to_post_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"results": []})

    source = TavilySearchSource(
        api_key="secret-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    options = SearchOptions(
        topic="news",
        time_range="week",
        include_domains=("example.com",),
        exclude_domains=("blocked.example",),
        search_depth="advanced",
    )

    assert source.search("查询", 7, options) == []
    assert captured["request"].method == "POST"
    assert str(captured["request"].url) == "https://api.tavily.com/search"
    assert captured["request"].headers["authorization"] == "Bearer secret-key"
    assert captured["payload"] == {
        "query": "查询",
        "max_results": 7,
        "topic": "news",
        "search_depth": "advanced",
        "time_range": "week",
        "include_domains": ["example.com"],
        "exclude_domains": ["blocked.example"],
    }


def test_tavily_source_omits_empty_optional_parameters():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"results": []})

    source = TavilySearchSource(
        api_key="key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    source.search("查询", 3, SearchOptions())

    assert payloads == [{
        "query": "查询",
        "max_results": 3,
        "topic": "general",
        "search_depth": "basic",
    }]


def test_tavily_source_maps_response_fields_truncates_and_respects_limit():
    response = {
        "results": [
            {
                "title": "First",
                "url": "https://example.com/first",
                "content": "123456",
                "published_date": "2026-08-21",
                "score": 0.9,
            },
            {"title": "Second", "url": "https://example.com/second", "content": "second"},
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)))
    source = TavilySearchSource(api_key="key", max_snippet_chars=4, http_client=client)

    results = source.search("查询", 1)

    assert len(results) == 1
    assert results[0].title == "First"
    assert results[0].url == "https://example.com/first"
    assert results[0].snippet == "1234"
    assert results[0].source == "tavily"
    assert results[0].published_date == "2026-08-21"
    assert results[0].score == 0.9


def test_tavily_source_filters_non_dict_and_missing_title_or_url():
    response = {
        "results": [
            "invalid",
            {"title": "", "url": "https://example.com/no-title"},
            {"title": "No URL"},
            {"title": "Valid", "url": "https://example.com/valid", "content": None},
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)))

    results = TavilySearchSource(api_key="key", http_client=client).search("查询", 5)

    assert [(result.title, result.snippet) for result in results] == [("Valid", "")]


def test_tavily_source_returns_empty_on_network_error_and_401():
    def network_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed", request=request)

    network_source = TavilySearchSource(
        api_key="do-not-leak",
        http_client=httpx.Client(transport=httpx.MockTransport(network_error)),
    )
    unauthorized_source = TavilySearchSource(
        api_key="do-not-leak",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401))),
    )

    assert network_source.search("查询", 5) == []
    assert unauthorized_source.search("查询", 5) == []


def test_tavily_source_returns_empty_on_invalid_json_or_result_shapes():
    responses = [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"results": {"title": "wrong"}}),
    ]

    for response in responses:
        client = httpx.Client(transport=httpx.MockTransport(lambda req, response=response: response))
        assert TavilySearchSource(api_key="key", http_client=client).search("查询", 5) == []


def test_bing_and_duckduckgo_accept_search_options_for_compatibility():
    options = SearchOptions(topic="news", search_depth="advanced")

    assert BingSearchSource(http_client=_client(BING_HTML)).search("查询", 1, options)[0].title == "结果 A"
    assert DuckDuckGoSearchSource(http_client=_client(DDG_HTML)).search("查询", 1, options)[0].title == "结果 A"


def test_tavily_source_owns_and_closes_only_client_it_creates(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr("iris_agent.web_search.sources.httpx.Client", FakeClient)

    owned_source = TavilySearchSource(api_key="key", timeout=9)
    owned_source.close()

    assert created[0].kwargs == {"timeout": 9, "follow_redirects": False}
    assert created[0].closed is True

    injected = FakeClient()
    injected_source = TavilySearchSource(api_key="key", http_client=injected)
    injected_source.close()
    assert injected.closed is False


@pytest.mark.parametrize("source_class", [BingSearchSource, DuckDuckGoSearchSource])
def test_html_search_sources_own_and_close_only_clients_they_create(monkeypatch, source_class):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr("iris_agent.web_search.sources.httpx.Client", FakeClient)

    owned_source = source_class(timeout=9)
    owned_source.close()
    assert created[0].closed is True

    injected = FakeClient()
    source_class(http_client=injected).close()
    assert injected.closed is False


def test_tavily_source_does_not_follow_redirects_even_with_redirecting_client():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(307, headers={"location": "https://other.example/search"})
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    source = TavilySearchSource(api_key="secret", http_client=client)

    assert source.search("查询", 5) == []
    assert len(requests) == 1
    assert b"secret" not in requests[0].content


@pytest.mark.parametrize(
    ("published_date", "score", "expected_date", "expected_score"),
    [
        ("2026-08-21", 2, "2026-08-21", 2.0),
        (123, "0.9", None, None),
        (None, True, None, None),
    ],
)
def test_tavily_source_normalizes_optional_metadata(
    published_date, score, expected_date, expected_score
):
    response = {
        "results": [{
            "title": "Valid",
            "url": "https://example.com",
            "content": "snippet",
            "published_date": published_date,
            "score": score,
        }]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)))

    result = TavilySearchSource(api_key="key", http_client=client).search("查询", 1)[0]

    assert result.published_date == expected_date
    assert result.score == expected_score


def test_tavily_source_only_swallows_transport_and_json_errors():
    class BrokenJsonResponse:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("malformed JSON")

    class BrokenJsonClient:
        def post(self, *args, **kwargs):
            return BrokenJsonResponse()

    class ProgrammingErrorClient:
        def post(self, *args, **kwargs):
            raise RuntimeError("programming error")

    assert TavilySearchSource(api_key="key", http_client=BrokenJsonClient()).search("查询", 1) == []
    with pytest.raises(RuntimeError, match="programming error"):
        TavilySearchSource(api_key="key", http_client=ProgrammingErrorClient()).search("查询", 1)


def test_tavily_source_does_not_expose_api_key_on_failure(capsys):
    api_key = "highly-secret-key"

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError(f"failed with {api_key}", request=request)

    source = TavilySearchSource(
        api_key=api_key,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert source.search("查询", 1) == []
    output = capsys.readouterr()
    assert api_key not in output.out
    assert api_key not in output.err
    assert not hasattr(source, "last_error")
    assert api_key.encode() not in requests[0].content


@pytest.mark.parametrize(
    ("source_class", "expected_source"),
    [(BingSearchSource, "bing"), (DuckDuckGoSearchSource, "duckduckgo")],
)
def test_html_sources_set_source_metadata(source_class, expected_source):
    html = BING_HTML if source_class is BingSearchSource else DDG_HTML

    result = source_class(http_client=_client(html)).search("查询", 1)[0]

    assert result.source == expected_source


@pytest.mark.parametrize("source_class", [BingSearchSource, DuckDuckGoSearchSource])
def test_html_sources_encode_domain_and_news_options_in_query(source_class):
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["q"])
        return httpx.Response(200, text="<html></html>")

    source = source_class(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    options = SearchOptions(
        topic="news",
        include_domains=("a.example", "b.example"),
        exclude_domains=("blocked.example",),
        search_depth="advanced",
    )

    source.search("base query", 5, options)

    assert queries == [
        "base query news (site:a.example OR site:b.example) -site:blocked.example"
    ]


@pytest.mark.parametrize("source_class", [BingSearchSource, DuckDuckGoSearchSource])
def test_html_sources_explicitly_reject_unsupported_time_range(source_class):
    source = source_class(http_client=_client("<html></html>"))

    with pytest.raises(ValueError, match="time_range"):
        source.search("查询", 5, SearchOptions(time_range="week"))
