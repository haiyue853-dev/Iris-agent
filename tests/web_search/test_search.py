from dataclasses import FrozenInstanceError

import httpx
import pytest

from iris_agent.web_search.models import SearchOptions, SearchResult
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


def test_search_result_to_dict_includes_non_empty_metadata():
    result = SearchResult(
        title="标题",
        url="https://x.com",
        snippet="摘要",
        source="example",
        published_date="2026-08-22",
        score=0.8,
    )

    assert result.to_dict() == {
        "title": "标题",
        "url": "https://x.com",
        "snippet": "摘要",
        "source": "example",
        "published_date": "2026-08-22",
        "score": 0.8,
    }


def test_search_result_to_dict_omits_empty_metadata_for_backward_compatibility():
    result = SearchResult("标题", "https://x.com", "摘要")

    assert result.to_dict() == {"title": "标题", "url": "https://x.com", "snippet": "摘要"}


def test_search_result_to_dict_includes_zero_score():
    result = SearchResult("标题", "https://x.com", "摘要", score=0.0)

    assert result.to_dict()["score"] == 0.0


def test_search_options_has_valid_defaults():
    options = SearchOptions()

    assert options.topic == "general"
    assert options.time_range is None
    assert options.include_domains == ()
    assert options.exclude_domains == ()
    assert options.search_depth == "basic"


def test_search_options_normalizes_domain_lists_to_tuples():
    options = SearchOptions(
        include_domains=["include.example"],
        exclude_domains=["exclude.example"],
    )

    assert options.include_domains == ("include.example",)
    assert options.exclude_domains == ("exclude.example",)


def test_search_options_fields_cannot_be_reassigned():
    options = SearchOptions()

    with pytest.raises(FrozenInstanceError):
        options.topic = "news"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("topic", "sports"),
        ("time_range", "hour"),
        ("search_depth", "deep"),
    ],
)
def test_search_options_rejects_invalid_enum_values(field, value):
    with pytest.raises(ValueError):
        SearchOptions(**{field: value})


@pytest.mark.parametrize("field", ["include_domains", "exclude_domains"])
def test_search_options_rejects_more_than_twenty_domains(field):
    domains = tuple(f"example{i}.com" for i in range(21))

    with pytest.raises(ValueError):
        SearchOptions(**{field: domains})


@pytest.mark.parametrize("field", ["include_domains", "exclude_domains"])
def test_search_options_accepts_exactly_twenty_domains(field):
    domains = [f"example{i}.com" for i in range(20)]

    options = SearchOptions(**{field: domains})

    assert getattr(options, field) == tuple(domains)


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "   ",
        "https://example.com",
        "example.com/path",
        "example.com:443",
        "user@example.com",
        "example.com?q=x",
        "example.com#part",
        "127.0.0.1",
        "2001:db8::1",
        f"{'a' * 250}.com",
    ],
)
def test_search_options_rejects_invalid_domains(domain):
    with pytest.raises(ValueError):
        SearchOptions(include_domains=[domain])


def test_search_options_normalizes_idn_and_removes_duplicates_in_order():
    domains = [" 例子.测试 ", "EXAMPLE.COM", "example.com", "例子.测试"]

    options = SearchOptions(include_domains=domains)

    assert options.include_domains == ("xn--fsqu00a.xn--0zwm56d", "example.com")
    assert domains == [" 例子.测试 ", "EXAMPLE.COM", "example.com", "例子.测试"]


def test_search_options_rejects_domain_over_253_raw_characters_before_trimming():
    domain = f"{' ' * 243}example.com"
    assert len(domain) == 254

    with pytest.raises(ValueError):
        SearchOptions(include_domains=[domain])


def test_search_options_accepts_valid_domain_at_253_character_boundary():
    domain = ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 61))
    assert len(domain) == 253

    options = SearchOptions(include_domains=[domain])

    assert options.include_domains == (domain,)


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


class StubSearchSource:
    def __init__(self, name, responses):
        self.name = name
        self.responses = iter(responses)
        self.calls = []

    def search(self, query, limit, options=None):
        self.calls.append((query, limit, options))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _result(url, *, title="title", snippet="snippet", score=None):
    return SearchResult(title=title, url=url, snippet=snippet, score=score)


def test_search_passes_same_options_and_retries_empty_source():
    options = SearchOptions(topic="news", time_range="week")
    source = StubSearchSource("stub", [[], [_result("https://example.com/item")]])
    client = WebSearchClient(sources=[source], max_retries=2)

    results = client.search("query", options=options)

    assert [result.url for result in results] == ["https://example.com/item"]
    assert source.calls == [("query", 5, options), ("query", 5, options)]


def test_search_stops_after_first_source_with_results():
    first = StubSearchSource("first", [[_result("https://first.example")]])
    second = StubSearchSource("second", [[_result("https://second.example")]])

    results = WebSearchClient(sources=[first, second]).search("query")

    assert [result.url for result in results] == ["https://first.example/"]
    assert second.calls == []


def test_search_falls_back_after_source_exception_without_leaking_details():
    secret = "api-key-super-secret"
    first = StubSearchSource("unsafe-source", [RuntimeError(secret), RuntimeError(secret)])
    second = StubSearchSource("safe-source", [[_result("https://safe.example")]])
    client = WebSearchClient(sources=[first, second])

    assert client.search("query")[0].url == "https://safe.example/"
    assert client.last_error is None
    assert len(first.calls) == 2

    failing = WebSearchClient(
        sources=[StubSearchSource("unsafe-source", [RuntimeError(secret), RuntimeError(secret)])]
    )
    assert failing.search("query") == []
    assert failing.last_error == "unsafe-source 无结果"
    assert secret not in failing.last_error


def test_search_normalizes_urls_deduplicates_and_keeps_best_result():
    source = StubSearchSource(
        "stub",
        [[
            _result("HTTP://Example.COM:80", title="old", snippet="short", score=0.4),
            _result("http://example.com/#fragment", title="best", snippet="longer", score=0.8),
            _result("https://EXAMPLE.com:443/path/", title="short", snippet="x", score=None),
            _result("https://example.com/path#part", title="long", snippet="a longer snippet", score=None),
            _result("https://example.com/path/?x=1#one", title="query-one", score=0.2),
            _result("https://example.com/path/?x=2#two", title="query-two", score=0.1),
        ]],
    )

    results = WebSearchClient(sources=[source], max_results=10).search("query")

    assert [(result.title, result.url) for result in results] == [
        ("best", "http://example.com/"),
        ("query-one", "https://example.com/path?x=1"),
        ("query-two", "https://example.com/path?x=2"),
        ("long", "https://example.com/path"),
    ]


def test_search_score_sort_is_stable_and_unscored_results_keep_source_order():
    source = StubSearchSource(
        "stub",
        [[
            _result("https://example.com/unscored-1", title="u1"),
            _result("https://example.com/scored-1", title="s1", score=0.5),
            _result("https://example.com/scored-2", title="s2", score=0.5),
            _result("https://example.com/high", title="high", score=0.9),
            _result("https://example.com/unscored-2", title="u2"),
        ]],
    )

    results = WebSearchClient(sources=[source]).search("query")

    assert [result.title for result in results] == ["high", "s1", "s2", "u1", "u2"]


@pytest.mark.parametrize("limit", [0, -1])
def test_search_non_positive_limit_returns_empty_without_calling_sources(limit):
    source = StubSearchSource("stub", [[_result("https://example.com")]])

    assert WebSearchClient(sources=[source]).search("query", limit=limit) == []
    assert source.calls == []


def test_search_caps_limit_at_max_results():
    source = StubSearchSource(
        "stub",
        [[_result(f"https://example.com/{index}") for index in range(10)]],
    )

    results = WebSearchClient(sources=[source], max_results=3).search("query", limit=99)

    assert len(results) == 3
    assert source.calls[0][1] == 3


def test_max_retries_is_normalized_to_at_least_one_attempt():
    source = StubSearchSource("stub", [[]])

    WebSearchClient(sources=[source], max_retries=0).search("query")

    assert len(source.calls) == 1


def test_search_supports_legacy_source_with_two_argument_search():
    class LegacySource:
        name = "legacy"

        def __init__(self):
            self.calls = []

        def search(self, query, limit):
            self.calls.append((query, limit))
            return [_result("https://legacy.example/result")]

    source = LegacySource()

    results = WebSearchClient(sources=[source]).search(
        "query", options=SearchOptions(topic="news")
    )

    assert [result.url for result in results] == ["https://legacy.example/result"]
    assert source.calls == [("query", 5)]


def test_search_default_max_retries_attempts_empty_source_twice():
    source = StubSearchSource("stub", [[], []])

    assert WebSearchClient(sources=[source]).search("query") == []

    assert len(source.calls) == 2


def test_search_normalizes_ipv6_hosts_and_ports():
    source = StubSearchSource(
        "stub",
        [[
            _result("HTTP://[2001:DB8::1]:80/path", title="default"),
            _result("https://[2001:DB8::2]:8443/path", title="custom"),
        ]],
    )

    results = WebSearchClient(sources=[source]).search("query")

    assert [result.url for result in results] == [
        "http://[2001:db8::1]/path",
        "https://[2001:db8::2]:8443/path",
    ]


def test_search_removes_url_credentials_from_results():
    source = StubSearchSource(
        "stub",
        [[_result("https://user:secret@Example.COM/path", title="safe")]],
    )

    results = WebSearchClient(sources=[source]).search("query")

    assert results[0].url == "https://example.com/path"
    assert "secret" not in results[0].url


def test_search_reports_when_no_sources_are_available():
    client = WebSearchClient(sources=[])

    assert client.search("query") == []
    assert client.last_error == "没有可用搜索源"


def test_search_calls_uninspectable_source_once_with_modern_protocol():
    class UninspectableSearch:
        __signature__ = object()

        def __init__(self):
            self.calls = []

        def __call__(self, query, limit, options=None):
            self.calls.append((query, limit, options))
            return [_result("https://modern.example/result")]

    class Source:
        name = "modern"

        def __init__(self):
            self.search = UninspectableSearch()

    source = Source()
    options = SearchOptions(topic="news")

    results = WebSearchClient(sources=[source]).search("query", options=options)

    assert results[0].url == "https://modern.example/result"
    assert source.search.calls == [("query", 5, options)]


def test_search_supports_keyword_only_options():
    class KeywordOnlySource:
        name = "keyword-only"

        def __init__(self):
            self.options = None

        def search(self, query, limit, *, options=None):
            self.options = options
            return [_result("https://keyword.example/result")]

    source = KeywordOnlySource()
    options = SearchOptions(topic="news")

    results = WebSearchClient(sources=[source]).search("query", options=options)

    assert results[0].url == "https://keyword.example/result"
    assert source.options is options


def test_search_stops_fallback_on_unsupported_filter_value_error():
    secret = "api-key-must-not-leak"
    tavily = StubSearchSource("Tavily", [[], []])
    bing = StubSearchSource("Bing", [ValueError(f"unsupported time_range {secret}")])
    ddg = StubSearchSource("DuckDuckGo", [[_result("https://ddg.example/result")]])
    client = WebSearchClient(sources=[tavily, bing, ddg])

    assert client.search("query", options=SearchOptions(time_range="week")) == []

    assert len(tavily.calls) == 2
    assert len(bing.calls) == 1
    assert ddg.calls == []
    assert "Bing" in client.last_error
    assert "不支持" in client.last_error
    assert "时间范围" in client.last_error
    assert secret not in client.last_error
