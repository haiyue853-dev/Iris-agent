from __future__ import annotations

import argparse
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository

MAX_BYTES = 1_500_000
QUESTION = re.compile(r"^(?:q(?:uestion)?\s*[:：]|问(?:题)?\s*[:：]|题(?:目)?\s*[:：])\s*(.+)$", re.I)
ANSWER = re.compile(r"^(?:a(?:nswer)?\s*[:：]|答(?:案)?\s*[:：]|参考答案\s*[:：])\s*(.+)$", re.I)
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
    request = Request(_public_url(url), headers={"User-Agent": "Iris-Agent/0.1 (+interview-study)"})
    with build_opener(Redirects()).open(request, timeout=15) as response:
        if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}: raise ValueError("target is not HTML")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError("page is too large")
        return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def _extract(html: str, source_url: str, limit: int) -> list[dict[str, str]]:
    parser = TextParser(); parser.feed(html); parser.flush(); items = []; question = None
    for line in parser.lines:
        if match := QUESTION.match(line): question = match.group(1).strip()
        elif (match := ANSWER.match(line)) and question:
            answer = match.group(1).strip()
            if answer: items.append({"question": question, "answer": answer, "source_url": source_url})
            question = None
            if len(items) >= limit: break
    return items


def _content(value): return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _call(name, arguments, repository):
    if name == "search_interview_sources":
        topic = str(arguments.get("topic", "")).strip(); limit = min(max(int(arguments.get("max_results", 5)), 1), 10)
        html = _fetch(f"https://html.duckduckgo.com/html/?q={quote_plus(topic + ' 面试题 答案')}")
        matches = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
        results = [{"url": unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0]), "title": re.sub(r"<.*?>", "", title).strip()} for url, title in matches[:limit]]
        return _content({"topic": topic, "results": results})
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
