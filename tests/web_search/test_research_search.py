import httpx

from iris_agent.web_search.models import SearchOptions, SearchResult
from iris_agent.web_search.search import WebSearchClient
from iris_agent.web_search.sources import TavilySearchSource


def test_empty_response_is_not_retried():
    class Empty:
        name = 'empty'
        calls = 0
        def search(self, query, limit, options=None):
            self.calls += 1
            return []
    source = Empty()
    client = WebSearchClient(sources=[source])
    assert client.search('query') == []
    assert source.calls == 1
    assert client.last_error is None


def test_unsupported_source_is_skipped_without_dropping_filters():
    class Unsupported:
        name = 'html'
        supports_options = frozenset()
        def search(self, *args):
            raise AssertionError('must not call an unsupported backend')
    class Supported:
        name = 'news'
        supports_options = frozenset({'time_range'})
        def search(self, query, limit, options=None):
            assert options.time_range == 'day'
            return [SearchResult('news', 'https://example.com', 'text')]
    client = WebSearchClient(sources=[Unsupported(), Supported()])
    assert client.search('query', options=SearchOptions(time_range='day'))
    assert client.last_metadata['source'] == 'news'


def test_auth_failure_is_not_retried_and_does_not_leak_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401, text='secret-value')
    source = TavilySearchSource('secret-value', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = WebSearchClient(sources=[source])
    assert client.search('query') == []
    assert len(calls) == 1
    assert client.last_error_code == 'search_auth_failed'
    assert 'secret-value' not in client.last_error


def test_transient_failure_retries_with_remaining_budget():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={'results': [{'title': 'title', 'url': 'https://example.com', 'content': 'body'}]})
    client = WebSearchClient(timeout=2, sources=[TavilySearchSource('key', http_client=httpx.Client(transport=httpx.MockTransport(handler)))])
    assert client.search('query')
    assert len(calls) == 2
    assert calls[1].extensions['timeout']['read'] <= calls[0].extensions['timeout']['read'] <= 2
