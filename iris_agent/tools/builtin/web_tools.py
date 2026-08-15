"""Web search + page fetch tools."""

from iris_agent.tools.base import Tool, ToolInvocationError
from iris_agent.web_search.fetcher import PageFetcher
from iris_agent.web_search.search import WebSearchClient


def build_web_search_tool(client: WebSearchClient) -> Tool:
    def web_search(query: str, limit: int | None = None):
        results = client.search(query, limit)
        if results:
            return {"results": [result.to_dict() for result in results]}
        if client.last_error:
            raise ToolInvocationError("web_search_failed", client.last_error)
        return {"results": []}

    return Tool(
        "web_search",
        "联网搜索，返回结果列表（标题、URL、摘要）",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回条数上限"},
            },
            "required": ["query"],
        },
        web_search,
        requires_approval=False,
    )


def build_fetch_page_tool(fetcher: PageFetcher) -> Tool:
    def fetch_page(url: str):
        text = fetcher.fetch(url)
        return {"text": text}

    return Tool(
        "fetch_page",
        "抓取指定网页并提取正文纯文本",
        {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "网页 URL"}},
            "required": ["url"],
        },
        fetch_page,
        requires_approval=False,
    )
