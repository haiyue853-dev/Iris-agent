"""Web search + page fetch tools."""

from concurrent.futures import ThreadPoolExecutor
from inspect import signature
import re
from urllib.parse import urlparse

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


def _fetch_page_text(fetcher: PageFetcher, url: str, query_hint: str | None, *, summarize: bool) -> str:
    fetch = fetcher.fetch
    try:
        fetch_signature = signature(fetch)
        fetch_signature.bind(url, query_hint=query_hint, summarize=summarize)
    except (TypeError, ValueError):
        return fetch(url, query_hint=query_hint)
    return fetch(url, query_hint=query_hint, summarize=summarize)


def _extract_canonical_urls(text: str) -> list[str]:
    candidates = re.findall(r"\]\((https?://[^\s)]+)\)", text, flags=re.IGNORECASE)
    candidates.extend(re.findall(r"https?://[^\s\])>]+", text, flags=re.IGNORECASE))
    urls = []
    for candidate in candidates:
        unescaped = re.sub(r"\\([\\`*{}\[\]()#+\-.!_>])", r"\1", candidate)
        parsed = urlparse(unescaped)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        canonical = parsed._replace(fragment="").geturl()
        if canonical not in urls:
            urls.append(canonical)
    return urls


def build_fetch_page_tool(fetcher: PageFetcher) -> Tool:
    def fetch_page(url: str, query_hint: str | None = None, content_mode: str = "summary"):
        text = _fetch_page_text(
            fetcher,
            url,
            query_hint,
            summarize=content_mode != "full",
        )
        return {"text": text}

    return Tool(
        "fetch_page",
        "抓取指定网页并提取正文纯文本。默认返回摘要；用户要求完整页面、面试问题与答案或入库素材时，将 content_mode 设为 full。",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页 URL"},
                "query_hint": {
                    "type": "string",
                    "description": "可选：当前用户的搜索意图关键词，用于让摘要更聚焦",
                },
                "content_mode": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "summary 返回摘要；full 返回完整正文",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        fetch_page,
        requires_approval=False,
    )


def build_collect_interview_knowledge_tool(client: WebSearchClient, fetcher: PageFetcher) -> Tool:
    def fetch_full_page(url: str, query_hint: str) -> str:
        return _fetch_page_text(fetcher, url, query_hint, summarize=False)

    def collect_interview_knowledge(query: str, category: str = "面经"):
        normalized_query = query.strip()
        if not normalized_query:
            raise ToolInvocationError("invalid_search_query", "搜索关键词不能为空")

        direct_urls = _extract_canonical_urls(normalized_query)[:2]
        if direct_urls:
            selected = [
                (urlparse(url).netloc or "指定网页", url, "")
                for url in direct_urls
            ]
        else:
            results = client.search(normalized_query, 3)
            if not results:
                if client.last_error:
                    raise ToolInvocationError("web_search_failed", client.last_error)
                raise ToolInvocationError("no_search_results", "没有找到可用于整理的面试资料")
            selected = [(result.title, result.url, result.snippet) for result in results[:2]]

        with ThreadPoolExecutor(max_workers=len(selected), thread_name_prefix="iris-interview") as executor:
            futures = [executor.submit(fetch_full_page, url, normalized_query) for _, url, _ in selected]
            pages = []
            for source, future in zip(selected, futures, strict=True):
                try:
                    pages.append((source, future.result()))
                except Exception:
                    pages.append((source, ""))

        topic = re.sub(r"\[[^\]]+\]\([^)]+\)", "", normalized_query)
        topic = re.sub(r"https?://[^\s\])>]+", "", topic)
        topic = re.sub(r"^\s*\d+\s*", "", topic).strip(" []()：:") or "面试问答"
        sections = [f"# {topic} 面试题与答案整理"]
        for (title, url, snippet), page in pages:
            sections.append(f"## {title}\n来源：{url}\n\n{page or snippet}")
        content = "\n\n".join(sections)[:50_000]
        return {
            "__irisKind": "knowledge-draft",
            "title": f"{topic} 面试题与答案整理"[:200],
            "content": content,
            "category": category,
            "source_url": selected[0][1],
        }

    return Tool(
        "collect_interview_knowledge",
        "搜集完整的面试问题与对应答案并生成待审核知识库草稿。用户给出网页链接时优先完整抓取直链且不做摘要；否则只搜索一次并并行抓取最多两页。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "面试题或面经搜索主题"},
                "category": {"type": "string", "description": "知识分类，默认「面经」"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        collect_interview_knowledge,
        requires_approval=False,
    )
