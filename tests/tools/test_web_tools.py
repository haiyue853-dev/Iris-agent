from iris_agent.tools.builtin.web_tools import build_fetch_page_tool, build_web_search_tool
from iris_agent.tools.registry import ToolRegistry
from iris_agent.web_search.models import SearchResult


class FakeClient:
    def search(self, query, limit=None):
        return [SearchResult(title="标题", url="https://x.com", snippet="摘要")]


class ErrorClient:
    def __init__(self):
        self.last_error = None

    def search(self, query, limit=None):
        self.last_error = "搜索请求失败: 连接超时"
        return []


class FakeFetcher:
    def __init__(self, text: str):
        self.text = text

    def fetch(self, url):
        return self.text


class RaisingFetcher:
    def fetch(self, url):
        raise ValueError("禁止访问内网地址")


def test_web_search_tool_returns_results():
    tool = build_web_search_tool(FakeClient())

    result = tool.invoke({"query": "面试经验"})

    assert result.ok
    assert result.value["results"] == [{"title": "标题", "url": "https://x.com", "snippet": "摘要"}]


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
