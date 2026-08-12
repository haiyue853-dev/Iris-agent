from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository
from iris_agent.tools.base import Tool, ToolInvocationError

MAX_RESPONSE_BYTES = 1_500_000
QUESTION = re.compile(r"^(?:q(?:uestion)?\s*[:：]|问(?:题)?\s*[:：]|(?:面试)?题(?:目)?\s*[:：])\s*(.+)$", re.I)
ANSWER = re.compile(r"^(?:a(?:nswer)?\s*[:：]|答(?:案)?\s*[:：]|参考答案\s*[:：])\s*(.+)$", re.I)


class TextParser(HTMLParser):
    blocks = {"p", "div", "li", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}: self.ignored += 1
        if tag in self.blocks: self.flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.ignored: self.ignored -= 1
        if tag in self.blocks: self.flush()

    def handle_data(self, data: str) -> None:
        if not self.ignored: self.parts.append(data)

    def flush(self) -> None:
        line = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        if line: self.lines.append(line)
        self.parts = []


def extract_qa_pairs(html: str, source_url: str, max_items: int = 20) -> list[dict[str, str]]:
    parser = TextParser(); parser.feed(html); parser.flush()
    items: list[dict[str, str]] = []; question: str | None = None
    for line in parser.lines:
        if match := QUESTION.match(line): question = match.group(1).strip()
        elif (match := ANSWER.match(line)) and question:
            answer = match.group(1).strip()
            if answer: items.append({"question": question, "answer": answer, "source_url": source_url})
            question = None
            if len(items) == max_items: break
    return items


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.hostname.casefold() == "localhost":
        raise ToolInvocationError("unsafe_url", "仅支持公开的 HTTP 或 HTTPS 网页地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ToolInvocationError("unreachable_url", "无法解析网页地址") from exc
    if any(ipaddress.ip_address(item[4][0]).is_private or ipaddress.ip_address(item[4][0]).is_loopback for item in addresses):
        raise ToolInvocationError("unsafe_url", "不允许访问本机或私有网络地址")
    return url


class PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_html(url: str) -> str:
    request = Request(validate_public_url(url), headers={"User-Agent": "Iris-Agent/0.1 (+interview-study)"})
    try:
        with build_opener(PublicRedirectHandler()).open(request, timeout=15) as response:
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise ToolInvocationError("unsupported_content", "目标地址不是 HTML 网页")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES: raise ToolInvocationError("page_too_large", "网页内容过大")
            return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except ToolInvocationError: raise
    except OSError as exc: raise ToolInvocationError("web_request_failed", "网页请求失败") from exc


def _result_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    destination = parse_qs(parsed.query).get("uddg", [None])[0]
    return unquote(destination) if destination else raw_url


def search_public_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    if not query.strip() or len(query) > 300:
        raise ToolInvocationError("invalid_query", "搜索词不能为空且不能超过 300 个字符")
    html = fetch_html(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}")
    results = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S)
    return [
        {"url": _result_url(url), "title": re.sub(r"<.*?>", "", title).strip()}
        for url, title in results[:max(1, min(max_results, 10))]
    ]


def build_web_search_tool() -> Tool:
    def search_web(query: str, max_results: int = 5) -> dict[str, Any]:
        if not query.strip() or len(query) > 300: raise ToolInvocationError("invalid_query", "搜索词不能为空且不能超过 300 个字符")
        return {"query": query, "results": search_public_web(query, max_results)}
    return Tool("search_web", "搜索公开网页，寻找含明确问题与答案的面试资料。", {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}, search_web)


def build_extract_interview_qa_tool() -> Tool:
    def extract_interview_qa(url: str, max_items: int = 20) -> dict[str, Any]:
        items = extract_qa_pairs(fetch_html(url), url, max(1, min(max_items, 50)))
        return {"source_url": url, "items": items, "count": len(items)}
    return Tool("extract_interview_qa", "仅抓取网页中明确标注为问题/Q和答案/A的面试问答对。", {"type": "object", "properties": {"url": {"type": "string"}, "max_items": {"type": "integer"}}, "required": ["url"]}, extract_interview_qa)


def build_save_interview_qa_tool(repository: InterviewKnowledgeRepository) -> Tool:
    def save_interview_qa(topic: str, items: list[dict[str, str]]) -> dict[str, int]:
        if len(items) > 50: raise ToolInvocationError("too_many_items", "一次最多保存 50 条问答")
        try: return repository.save(topic, items)
        except ValueError as exc: raise ToolInvocationError("knowledge_save_failed", str(exc)) from exc
    item = {"type": "object", "properties": {"question": {"type": "string"}, "answer": {"type": "string"}, "source_url": {"type": "string"}}, "required": ["question", "answer", "source_url"]}
    return Tool("save_interview_qa", "保存已抓取的问答；只保存题目、答案与来源，不能保存介绍或目录。", {"type": "object", "properties": {"topic": {"type": "string"}, "items": {"type": "array", "items": item}}, "required": ["topic", "items"]}, save_interview_qa)
