from iris_agent.tools.builtin.web_tools import build_collect_interview_knowledge_tool, build_fetch_page_tool, build_web_search_tool
from iris_agent.tools.registry import ToolRegistry
from iris_agent.web_search.models import SearchResult


class FakeClient:
    def search(self, query, limit=None):
        return [SearchResult(title="标题", url="https://x.com", snippet="摘要")]


class OptionsClient:
    def __init__(self):
        self.calls = []
        self.last_error = None

    def search(self, query, limit=None, options=None):
        self.calls.append((query, limit, options))
        return [
            SearchResult(
                title="新闻",
                url="https://example.com/news",
                snippet="摘要",
                source="example",
                published_date="2026-08-22",
                score=0.9,
            )
        ]


class ErrorClient:
    def __init__(self):
        self.last_error = None

    def search(self, query, limit=None):
        self.last_error = "搜索请求失败: 连接超时"
        return []


class FakeFetcher:
    def __init__(self, text: str):
        self.text = text

    def fetch(self, url, query_hint=None):
        return self.text


class RaisingFetcher:
    def fetch(self, url, query_hint=None):
        raise ValueError("禁止访问内网地址")


def test_web_search_tool_returns_results():
    tool = build_web_search_tool(FakeClient())

    result = tool.invoke({"query": "面试经验"})

    assert result.ok
    assert result.value["results"] == [{"title": "标题", "url": "https://x.com", "snippet": "摘要"}]


def test_web_search_passes_advanced_options_and_returns_metadata():
    client = OptionsClient()
    tool = build_web_search_tool(client)

    result = tool.invoke(
        {
            "query": "发布会",
            "limit": 3,
            "topic": "news",
            "time_range": "week",
            "include_domains": ["example.com"],
            "exclude_domains": ["spam.example"],
            "search_depth": "advanced",
        }
    )

    assert result.ok
    query, limit, options = client.calls[0]
    assert (query, limit) == ("发布会", 3)
    assert options.topic == "news"
    assert options.time_range == "week"
    assert options.include_domains == ("example.com",)
    assert options.exclude_domains == ("spam.example",)
    assert options.search_depth == "advanced"
    assert result.value["results"][0] == {
        "title": "新闻",
        "url": "https://example.com/news",
        "snippet": "摘要",
        "source": "example",
        "published_date": "2026-08-22",
        "score": 0.9,
    }


def test_web_search_passes_default_options():
    client = OptionsClient()

    result = build_web_search_tool(client).invoke({"query": "默认搜索"})

    assert result.ok
    _, _, options = client.calls[0]
    assert options.topic == "general"
    assert options.time_range is None
    assert options.include_domains == ()
    assert options.exclude_domains == ()
    assert options.search_depth == "basic"


def test_web_search_validates_query_without_changing_its_whitespace():
    client = OptionsClient()
    tool = build_web_search_tool(client)

    empty = tool.invoke({"query": " \t\n "})
    too_long = tool.invoke({"query": "x" * 501})
    valid = tool.invoke({"query": "  保留空格  "})

    assert empty.error_code == "invalid_search_query"
    assert too_long.error_code == "invalid_search_query"
    assert valid.ok
    assert client.calls[0][0] == "  保留空格  "


def test_web_search_validates_limit_boundaries():
    tool = build_web_search_tool(OptionsClient())

    assert tool.invoke({"query": "x", "limit": 1}).ok
    assert tool.invoke({"query": "x", "limit": 20}).ok
    assert tool.invoke({"query": "x", "limit": 0}).error_code == "invalid_search_options"
    assert tool.invoke({"query": "x", "limit": 21}).error_code == "invalid_search_options"


def test_web_search_uses_configured_default_depth():
    client = OptionsClient()

    result = build_web_search_tool(client, default_search_depth="advanced").invoke(
        {"query": "深度搜索"}
    )

    assert result.ok
    assert client.calls[0][2].search_depth == "advanced"


def test_web_search_explicit_depth_overrides_configured_default():
    client = OptionsClient()

    result = build_web_search_tool(client, default_search_depth="advanced").invoke(
        {"query": "快速搜索", "search_depth": "basic"}
    )

    assert result.ok
    assert client.calls[0][2].search_depth == "basic"


def test_web_search_supports_legacy_two_argument_client():
    result = build_web_search_tool(FakeClient()).invoke({"query": "兼容", "topic": "news"})

    assert result.ok


def test_web_search_does_not_hide_client_internal_type_error():
    class BrokenClient:
        last_error = None

        def search(self, query, limit=None, options=None):
            raise TypeError("客户端内部错误")

    result = build_web_search_tool(BrokenClient()).invoke({"query": "错误"})

    assert not result.ok
    assert result.error_code == "tool_execution_error"
    assert result.error_message == "客户端内部错误"


def test_web_search_uses_modern_protocol_when_signature_cannot_be_inspected():
    class UninspectableSearch:
        def __init__(self):
            self.calls = []

        @property
        def __signature__(self):
            raise ValueError("签名不可用")

        def __call__(self, query, limit=None, options=None):
            self.calls.append((query, limit, options))
            return [SearchResult(title="结果", url="https://example.com", snippet="摘要")]

    class Client:
        last_error = None
        search = UninspectableSearch()

    client = Client()
    result = build_web_search_tool(client).invoke({"query": "不可检查", "limit": 2})

    assert result.ok
    assert len(client.search.calls) == 1
    assert client.search.calls[0][0:2] == ("不可检查", 2)
    assert client.search.calls[0][2].topic == "general"


def test_web_search_supports_keyword_only_limit_and_options():
    class KeywordOnlyClient:
        last_error = None

        def __init__(self):
            self.call = None

        def search(self, query, *, limit=None, options=None):
            self.call = (query, limit, options)
            return [SearchResult(title="结果", url="https://example.com", snippet="摘要")]

    client = KeywordOnlyClient()
    result = build_web_search_tool(client).invoke(
        {"query": "关键词", "limit": 4, "search_depth": "advanced"}
    )

    assert result.ok
    assert client.call[0:2] == ("关键词", 4)
    assert client.call[2].search_depth == "advanced"


def test_web_search_reports_invalid_option_values():
    tool = build_web_search_tool(OptionsClient())

    invalid_enum = tool.invoke({"query": "x", "topic": "images"})
    too_many_domains = tool.invoke(
        {"query": "x", "include_domains": [f"domain-{index}.example" for index in range(21)]}
    )

    assert invalid_enum.error_code == "invalid_search_options"
    assert too_many_domains.error_code == "invalid_search_options"
    assert invalid_enum.error_message == "搜索选项无效，请检查主题、时间范围、搜索深度和域名数量"


def test_web_search_schema_describes_search_options():
    parameters = build_web_search_tool(OptionsClient()).parameters

    assert parameters["required"] == ["query"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["query"]["minLength"] == 1
    assert parameters["properties"]["query"]["maxLength"] == 500
    assert parameters["properties"]["limit"]["minimum"] == 1
    assert parameters["properties"]["limit"]["maximum"] == 20
    assert parameters["properties"]["topic"]["enum"] == ["general", "news"]
    assert parameters["properties"]["time_range"]["enum"] == ["day", "week", "month", "year"]
    assert parameters["properties"]["search_depth"]["enum"] == ["basic", "advanced"]
    for name in ("include_domains", "exclude_domains"):
        assert parameters["properties"][name]["items"]["type"] == "string"
        assert parameters["properties"][name]["items"]["minLength"] == 1
        assert parameters["properties"][name]["items"]["maxLength"] == 253
        assert parameters["properties"][name]["maxItems"] == 20


def test_web_search_requires_query():
    registry = ToolRegistry()
    registry.register(build_web_search_tool(FakeClient()))

    result = registry.invoke("web_search", {})

    assert not result.ok
    assert result.error_code == "invalid_tool_arguments"


def test_web_search_tool_reports_error():
    tool = build_web_search_tool(ErrorClient())

    result = tool.invoke({"query": "面试经验"})

    assert not result.ok
    assert result.error_code == "web_search_failed"
    assert "连接超时" in result.error_message


def test_fetch_page_tool_returns_text():
    tool = build_fetch_page_tool(FakeFetcher("正文内容"))

    result = tool.invoke({"url": "https://example.com/page"})

    assert result.ok
    assert result.value["text"] == "正文内容"


def test_fetch_page_tool_can_return_full_content_without_summarizing():
    class FullContentFetcher:
        def __init__(self):
            self.calls = []

        def fetch(self, url, query_hint=None, summarize=True):
            self.calls.append((url, query_hint, summarize))
            return "完整问题与答案"

    fetcher = FullContentFetcher()
    tool = build_fetch_page_tool(fetcher)

    result = tool.invoke({
        "url": "https://example.com/interview",
        "query_hint": "抓取面试问题加答案",
        "content_mode": "full",
    })

    assert result.ok
    assert result.value["text"] == "完整问题与答案"
    assert fetcher.calls == [
        ("https://example.com/interview", "抓取面试问题加答案", False)
    ]


def test_fetch_page_tool_requires_url():
    registry = ToolRegistry()
    registry.register(build_fetch_page_tool(FakeFetcher("正文")))

    result = registry.invoke("fetch_page", {})

    assert not result.ok
    assert result.error_code == "invalid_tool_arguments"


def test_fetch_page_tool_reports_error():
    tool = build_fetch_page_tool(RaisingFetcher())

    result = tool.invoke({"url": "http://127.0.0.1/x"})

    assert not result.ok
    assert "内网" in result.error_message


def test_collect_interview_knowledge_searches_once_fetches_two_pages_and_returns_a_draft():
    class SearchClient:
        last_error = None

        def __init__(self):
            self.calls = []

        def search(self, query, limit=None):
            self.calls.append((query, limit))
            return [
                SearchResult(title="题目一", url="https://example.com/1", snippet="摘要一"),
                SearchResult(title="题目二", url="https://example.com/2", snippet="摘要二"),
                SearchResult(title="题目三", url="https://example.com/3", snippet="摘要三"),
            ]

    class Fetcher:
        def __init__(self):
            self.calls = []

        def fetch(self, url, query_hint=None):
            self.calls.append((url, query_hint))
            return f"{url} 的正文"

    client = SearchClient()
    fetcher = Fetcher()

    result = build_collect_interview_knowledge_tool(client, fetcher).invoke({"query": "LLM 面试题"})

    assert result.ok
    assert client.calls == [("LLM 面试题", 3)]
    assert set(fetcher.calls) == {
        ("https://example.com/1", "LLM 面试题"),
        ("https://example.com/2", "LLM 面试题"),
    }
    assert result.value["__irisKind"] == "knowledge-draft"
    assert result.value["source_url"] == "https://example.com/1"
    assert "题目一" in result.value["content"]
    assert "题目二" in result.value["content"]
    assert "题目三" not in result.value["content"]


def test_collect_interview_knowledge_prioritizes_direct_url_and_keeps_full_qa_content():
    class SearchClient:
        last_error = None

        def __init__(self):
            self.calls = []

        def search(self, query, limit=None):
            self.calls.append((query, limit))
            return []

    class Fetcher:
        def __init__(self):
            self.calls = []

        def fetch(self, url, query_hint=None, summarize=True):
            self.calls.append((url, query_hint, summarize))
            return "1. 什么是 Agentic RAG？\n答案：它会动态规划并按需重新检索。"

    client = SearchClient()
    fetcher = Fetcher()
    query = "抓取问题加答案 https://notes.example.com/rag.html#agent"

    result = build_collect_interview_knowledge_tool(client, fetcher).invoke({"query": query})

    assert result.ok
    assert client.calls == []
    assert fetcher.calls == [("https://notes.example.com/rag.html", query, False)]
    assert "什么是 Agentic RAG" in result.value["content"]
    assert "动态规划并按需重新检索" in result.value["content"]
    assert result.value["source_url"] == "https://notes.example.com/rag.html"


def test_collect_interview_knowledge_normalizes_markdown_url_and_fetches_it_once():
    class SearchClient:
        last_error = None

        def search(self, query, limit=None):
            raise AssertionError("直链不应触发搜索")

    class Fetcher:
        def __init__(self):
            self.calls = []

        def fetch(self, url, query_hint=None, summarize=True):
            self.calls.append((url, query_hint, summarize))
            return "问题：RAG 的幻觉怎么处理？\n答案：提升召回质量并约束生成。"

    query = (
        r"1[https://notes.kamacoder.com/interview/llm/rag\_interview.html#\_9-rag-"
        r"%E7%9A%84%E5%B9%BB%E8%A7%89%E6%80%8E%E4%B9%88%E5%A4%84%E7%90%86"
        r"抓取这个页面的面试经验](https://notes.kamacoder.com/interview/llm/rag_interview.html#_9-rag-"
        r"%E7%9A%84%E5%B9%BB%E8%A7%89%E6%80%8E%E4%B9%88%E5%A4%84%E7%90%86"
        r"抓取这个页面的面试经验)"
    )
    fetcher = Fetcher()

    result = build_collect_interview_knowledge_tool(SearchClient(), fetcher).invoke(
        {"query": query}
    )

    canonical_url = "https://notes.kamacoder.com/interview/llm/rag_interview.html"
    assert result.ok
    assert fetcher.calls == [(canonical_url, query, False)]
    assert result.value["source_url"] == canonical_url
    assert "RAG 的幻觉怎么处理" in result.value["content"]
