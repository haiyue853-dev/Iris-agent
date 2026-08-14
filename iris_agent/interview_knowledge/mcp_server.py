from __future__ import annotations

import argparse
import base64
import html
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import sys
from xml.etree import ElementTree
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository

MAX_BYTES = 3_000_000
QUESTION = re.compile(r"^(?:q(?:uestion)?\s*[:：]|问(?:题)?\s*[:：]|题(?:目)?\s*[:：])\s*(.+)$", re.I)
ANSWER = re.compile(r"^(?:a(?:nswer)?\s*[:：]|答(?:案)?\s*[:：]|参考答案\s*[:：])\s*(.+)$", re.I)
NUMBERED_QUESTION = re.compile(r"^(?:q(?:uestion)?\s*)?\d+\s*[.):\-]\s*(.+\?)\s*$", re.I)
TOOLS = [
    {"name": "search_interview_sources", "description": "Search public pages for interview questions with answers.", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["topic"]}, "annotations": {"readOnlyHint": True}},
    {"name": "extract_interview_qa", "description": "Extract only explicitly labeled question and answer pairs from a public HTML page.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "max_items": {"type": "integer"}}, "required": ["url"]}, "annotations": {"readOnlyHint": True}},
    {"name": "save_interview_qa", "description": "Save complete interview question and answer pairs to the local knowledge base.", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "items": {"type": "array"}}, "required": ["topic", "items"]}},
]


class TextParser(HTMLParser):
    blocks = {"p", "div", "li", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "br"}
    def __init__(self): super().__init__(); self.lines = []; self.parts = []; self.ignored = 0
    def handle_starttag(self, tag, attrs):
        self.ignored += tag in {"script", "style", "noscript"}
        if tag in self.blocks: self.flush()
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.ignored: self.ignored -= 1
        if tag in self.blocks: self.flush()
    def handle_data(self, data):
        if not self.ignored: self.parts.append(data)
    def flush(self):
        line = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        if line: self.lines.append(line)
        self.parts = []


def _public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.hostname.casefold() == "localhost": raise ValueError("only public HTTP(S) URLs are supported")
    try: addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc: raise ValueError("URL cannot be resolved") from exc
    if any(ipaddress.ip_address(item[4][0]).is_private or ipaddress.ip_address(item[4][0]).is_loopback for item in addresses): raise ValueError("private network URLs are not allowed")
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): _public_url(newurl); return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> str:
    request = Request(_public_url(url), headers={
        "User-Agent": "Mozilla/5.0 (compatible; Iris-Agent/0.1; +interview-study)",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    })
    with build_opener(Redirects()).open(request, timeout=15) as response:
        try:
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset()
        except UnicodeError:
            content_type = "text/html"
            charset = None
        if content_type not in {"text/html", "application/xhtml+xml", "text/xml", "application/xml", "application/rss+xml"}: raise ValueError("target is not HTML or XML")
        raw = response.read(MAX_BYTES)
        return _decode_html(raw, charset)


def _decode_html(raw: bytes, declared_charset: str | None) -> str:
    encodings = [declared_charset, "utf-8", "gb18030"]
    for encoding in dict.fromkeys(item for item in encodings if item):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _search_sources(topic: str, limit: int) -> list[dict[str, str]]:
    query = quote_plus(_search_query(topic))
    failures: list[str] = []
    try:
        rss_results = _parse_bing_rss(_fetch(f"https://www.bing.com/search?format=rss&q={query}&setlang=en-US&cc=us"))
    except (OSError, UnicodeError, ValueError, ElementTree.ParseError) as exc:
        failures.append(f"Bing RSS: {type(exc).__name__}")
    else:
        ranked = _rank_sources(rss_results, topic, limit)
        if ranked:
            return ranked
    for provider, url, pattern in (
        (
            "Bing",
            f"https://www.bing.com/search?q={query}&setlang=en-US&cc=us",
            r'<li[^>]*class="[^"]*b_algo[^"]*".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        ),
        (
            "DuckDuckGo",
            f"https://html.duckduckgo.com/html/?q={query}",
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        ),
    ):
        try:
            matches = re.findall(pattern, _fetch(url), re.S | re.I)
        except (OSError, UnicodeError) as exc:
            failures.append(f"{provider}: {type(exc).__name__}")
            continue
        results = []
        seen_urls: set[str] = set()
        for result_url, title in matches:
            resolved_url = _resolve_search_url(result_url)
            try:
                _public_url(resolved_url)
            except ValueError:
                continue
            if resolved_url in seen_urls:
                continue
            seen_urls.add(resolved_url)
            clean_title = html.unescape(re.sub(r"<.*?>", "", title)).strip()
            results.append({"url": resolved_url, "title": clean_title})
        if results:
            return _rank_sources(results, topic, limit)
    detail = ", ".join(failures) or "no results returned"
    raise OSError(f"public search is unavailable ({detail})")


def _search_query(topic: str) -> str:
    subject = re.sub(r"\b(?:interview|questions?|answers?|experience|and)\b", " ", topic, flags=re.I)
    subject = re.sub(r"面试(?:经验|题)?|问答|答案", " ", subject)
    subject = re.sub(r"\s+", " ", subject).strip() or topic.strip()
    return f'"{subject} interview questions"'


def _parse_bing_rss(value: str) -> list[dict[str, str]]:
    root = ElementTree.fromstring(value)
    results = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if title and url:
            results.append({"url": url, "title": title})
    return results


def _rank_sources(results: list[dict[str, str]], topic: str, limit: int) -> list[dict[str, str]]:
    unique = {item["url"]: item for item in results}
    ranked = sorted(unique.values(), key=lambda item: _source_relevance(item, topic), reverse=True)
    relevant = [item for item in ranked if _source_relevance(item, topic) > 0]
    return (relevant or ranked)[:limit]


def _resolve_search_url(value: str) -> str:
    value = html.unescape(value)
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    if parsed.hostname and parsed.hostname.casefold().endswith("bing.com") and parsed.path == "/ck/a":
        encoded = query.get("u", [""])[0]
        if encoded.startswith("a1"):
            payload = encoded[2:]
            try:
                return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
    return unquote(value)


def _source_relevance(item: dict[str, str], topic: str) -> int:
    text = f"{item['title']} {item['url']}".casefold()
    positive = ("interview", "question", "answer", "面试", "问答", "题解")
    negative = ("download", "oracle.com", "wikipedia", "compiler", "tutorial")
    score = sum(2 for marker in positive if marker in text)
    score -= sum(2 for marker in negative if marker in text)
    topic_words = re.findall(r"[a-z0-9+#.]{2,}", topic.casefold())
    score += sum(1 for word in topic_words if word in text)
    return score


def _extract(html: str, source_url: str, limit: int) -> list[dict[str, str]]:
    parser = TextParser(); parser.feed(html); parser.flush()
    items: list[dict[str, str]] = []
    question: str | None = None
    answer_parts: list[str] = []

    def commit() -> None:
        nonlocal question, answer_parts
        answer = " ".join(answer_parts).strip()
        if question and len(answer) >= 20:
            items.append({"question": question, "answer": answer[:4_000], "source_url": source_url})
        question = None
        answer_parts = []

    for line in parser.lines:
        question_match = QUESTION.match(line) or NUMBERED_QUESTION.match(line)
        if question_match:
            commit()
            if len(items) >= limit:
                break
            question = question_match.group(1).strip()
            continue
        if question:
            if answer_match := ANSWER.match(line):
                answer_parts.append(answer_match.group(1).strip())
            elif sum(map(len, answer_parts)) < 4_000:
                answer_parts.append(line)
    if len(items) < limit:
        commit()
    return items


def _content(value): return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _call(name, arguments, repository):
    if name == "search_interview_sources":
        topic = str(arguments.get("topic", "")).strip(); limit = min(max(int(arguments.get("max_results", 5)), 1), 10)
        return _content({"topic": topic, "results": _search_sources(topic, limit)})
    if name == "extract_interview_qa":
        url = str(arguments.get("url", "")); limit = min(max(int(arguments.get("max_items", 20)), 1), 50)
        items = _extract(_fetch(url), url, limit)
        return _content({"source_url": url, "items": items, "count": len(items)})
    if name == "save_interview_qa":
        items = arguments.get("items", [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items): raise ValueError("items must be an array")
        return _content(repository.save(str(arguments.get("topic", "")), items))
    raise ValueError("unknown tool")


def serve(path: Path):
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    repository = InterviewKnowledgeRepository(path)
    for line in sys.stdin:
        request = json.loads(line); request_id = request.get("id")
        try:
            if request.get("method") == "initialize": result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "iris-interview-web", "version": "1.0"}}
            elif request.get("method") == "tools/list": result = {"tools": TOOLS}
            elif request.get("method") == "tools/call":
                params = request.get("params", {}); result = _call(params.get("name"), params.get("arguments", {}), repository)
            elif request_id is None: continue
            else: raise ValueError("method not found")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, OSError, TypeError) as exc: response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n"); sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--knowledge-path", required=True); serve(Path(parser.parse_args().knowledge_path))
