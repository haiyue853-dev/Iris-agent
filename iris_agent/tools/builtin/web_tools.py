"""Web search + page fetch tools."""

from inspect import signature

from iris_agent.tools.base import Tool, ToolInvocationError
from iris_agent.web_search.fetcher import PageFetcher
from iris_agent.web_search.models import SearchOptions
from iris_agent.web_search.search import WebSearchClient


def build_web_search_tool(client: WebSearchClient, default_search_depth: str = "basic") -> Tool:
    def web_search(
        query: str,
        limit: int | None = None,
        topic: str = "general",
        time_range: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        search_depth: str | None = None,
    ):
        if not query.strip() or len(query) > 500:
            raise ToolInvocationError(
                "invalid_search_query",
                "搜索关键词不能为空且不能超过 500 个字符",
            )
        if limit is not None and not 1 <= limit <= 20:
            raise ToolInvocationError(
                "invalid_search_options",
                "搜索结果条数必须在 1 到 20 之间",
            )
        try:
            options = SearchOptions(
                topic=topic,
                time_range=time_range,
                include_domains=tuple(include_domains or ()),
                exclude_domains=tuple(exclude_domains or ()),
                search_depth=search_depth if search_depth is not None else default_search_depth,
            )
        except ValueError as exc:
            raise ToolInvocationError(
                "invalid_search_options",
                "搜索选项无效，请检查主题、时间范围、搜索深度和域名数量",
            ) from exc

        search = client.search
        try:
            search_signature = signature(search)
        except (TypeError, ValueError):
            results = search(query, limit, options)
        else:
            candidates = (
                ((query, limit, options), {}),
                ((query, limit), {"options": options}),
                ((query,), {"limit": limit, "options": options}),
                ((query, limit), {}),
                ((query,), {"limit": limit}),
            )
            for args, kwargs in candidates:
                try:
                    search_signature.bind(*args, **kwargs)
                except TypeError:
                    continue
                results = search(*args, **kwargs)
                break
            else:
                search_signature.bind(query, limit, options)
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
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "返回条数上限",
                },
                "topic": {
                    "type": "string",
                    "enum": ["general", "news"],
                    "description": "搜索主题",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "结果时间范围",
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 253},
                    "maxItems": 20,
                    "description": "仅搜索这些纯域名（不含协议、路径、端口或 IP）",
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 253},
                    "maxItems": 20,
                    "description": "排除这些纯域名（不含协议、路径、端口或 IP）",
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": f"搜索深度；省略时使用配置默认值 {default_search_depth}",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
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
