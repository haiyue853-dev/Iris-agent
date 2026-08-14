from __future__ import annotations

import json
import re
from typing import Any

from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository
from iris_agent.mcp_center.service import McpCenterService


class InterviewCollectionService:
    def __init__(self, mcp: McpCenterService, repository: InterviewKnowledgeRepository) -> None:
        self.mcp = mcp
        self.repository = repository

    def preview(self, topic: str, *, max_sources: int = 3, max_items_per_source: int = 10) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")
        max_sources = min(max(int(max_sources), 1), 5)
        max_items_per_source = min(max(int(max_items_per_source), 1), 20)

        search = self._payload(self.mcp.call_tool(
            "builtin-interview-web",
            "search_interview_sources",
            {"topic": topic, "max_results": max_sources},
        ))
        raw_sources = search.get("results", [])
        sources = [item for item in raw_sources if isinstance(item, dict) and isinstance(item.get("url"), str)][:max_sources]
        known = {
            self._question_key(str(item.get("question", "")))
            for item in self.repository.list(topic)
        }
        items: list[dict[str, str]] = []
        seen = set(known)
        source_reports: list[dict[str, Any]] = []
        duplicates = 0

        for source in sources:
            url = str(source["url"])
            report: dict[str, Any] = {"url": url, "title": str(source.get("title", "")), "status": "ok", "count": 0}
            try:
                extracted = self._payload(self.mcp.call_tool(
                    "builtin-interview-web",
                    "extract_interview_qa",
                    {"url": url, "max_items": max_items_per_source},
                ))
            except ValueError as exc:
                report["status"] = "failed"
                report["error"] = str(exc)[:200]
                source_reports.append(report)
                continue
            for raw_item in extracted.get("items", []):
                if not isinstance(raw_item, dict):
                    continue
                question = str(raw_item.get("question", "")).strip()
                answer = str(raw_item.get("answer", "")).strip()
                key = self._question_key(question)
                if len(question) < 4 or len(answer) < 20:
                    continue
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                items.append({"question": question, "answer": answer, "source_url": str(raw_item.get("source_url") or url)})
                report["count"] += 1
            source_reports.append(report)

        return {
            "topic": topic,
            "items": items,
            "sources": source_reports,
            "summary": {"sources": len(source_reports), "found": len(items), "duplicates": duplicates},
        }

    def save(self, topic: str, items: list[dict[str, object]]) -> dict[str, int]:
        return self.repository.save(topic, items)

    @staticmethod
    def _payload(result: object) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise ValueError("MCP returned an invalid result")
        content = result.get("content")
        if not isinstance(content, list):
            raise ValueError("MCP returned an invalid result")
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                try:
                    payload = json.loads(item["text"])
                except json.JSONDecodeError as exc:
                    raise ValueError("MCP returned invalid JSON") from exc
                if isinstance(payload, dict):
                    return payload
        raise ValueError("MCP returned an invalid result")

    @staticmethod
    def _question_key(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()
