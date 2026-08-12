from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository
from iris_agent.tools.builtin.web_interview import extract_qa_pairs, fetch_html, search_public_web


TOOLS = [
    {"name": "search_interview_sources", "description": "Search public web pages likely to contain interview questions and answers.", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["topic"]}, "annotations": {"readOnlyHint": True}},
    {"name": "extract_interview_qa", "description": "Extract only explicitly labelled question and answer pairs from a public HTML page.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "max_items": {"type": "integer"}}, "required": ["url"]}, "annotations": {"readOnlyHint": True}},
    {"name": "save_interview_qa", "description": "Save complete interview question and answer pairs to the local knowledge base.", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "items": {"type": "array"}}, "required": ["topic", "items"]}},
]


def _result(value: Any) -> dict[str, object]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _call(name: str, arguments: dict[str, object], repository: InterviewKnowledgeRepository) -> dict[str, object]:
    if name == "search_interview_sources":
        topic = str(arguments.get("topic", "")).strip()
        return _result({"topic": topic, "results": search_public_web(f"{topic} 面试题 答案", int(arguments.get("max_results", 5)))})
    if name == "extract_interview_qa":
        url = str(arguments.get("url", ""))
        items = extract_qa_pairs(fetch_html(url), url, min(max(int(arguments.get("max_items", 20)), 1), 50))
        return _result({"source_url": url, "items": items, "count": len(items)})
    if name == "save_interview_qa":
        topic = str(arguments.get("topic", ""))
        items = arguments.get("items", [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError("items must be an array of question and answer objects")
        return _result(repository.save(topic, items))
    raise ValueError("unknown tool")


def serve(knowledge_path: Path) -> None:
    repository = InterviewKnowledgeRepository(knowledge_path)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                response = {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "iris-interview-web", "version": "1.0"}}}
            elif method == "tools/list":
                response = {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
            elif method == "tools/call":
                params = request.get("params", {})
                response = {"jsonrpc": "2.0", "id": request_id, "result": _call(str(params.get("name", "")), dict(params.get("arguments", {})), repository)}
            elif request_id is not None:
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}
            else:
                continue
        except (TypeError, ValueError, OSError) as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id") if "request" in locals() else None, "error": {"code": -32000, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge-path", required=True)
    serve(Path(parser.parse_args().knowledge_path))
