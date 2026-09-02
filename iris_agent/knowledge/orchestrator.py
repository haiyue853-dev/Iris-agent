"""Unified retrieval planning across documents, memory, and session history."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from iris_agent.session_search.tokenizer import tokenize


_GLOBAL_TERMS = ("整体主题", "整体", "全局", "趋势", "冲突", "总结", "概括")
_RELATION_TERMS = ("关系", "关联", "联系", "影响", "依赖", "属于", "导致")
_PRECISE_TERMS = ("原文", "具体", "哪一段", "出处", "定义", "数值")
_VAGUE_TERMS = ("这个", "那个", "它", "该方案", "上述", "刚才", "之前", "上次", "这些资料", "这份资料", "上述资料")
_QUOTED = re.compile(r"[《“\"']([^》”\"']+)[》”\"']")
_ASCII_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]*")


@dataclass(frozen=True, slots=True)
class QueryPlan:
    original_query: str
    rewritten_query: str
    high_level_keywords: tuple[str, ...]
    low_level_keywords: tuple[str, ...]
    routes: tuple[str, ...]
    rag_mode: str


@dataclass(frozen=True, slots=True)
class UnifiedKnowledgeHit:
    source_type: str
    source_id: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any]


class KnowledgeOrchestrator:
    """Plan one query and assemble a bounded, cited context from existing stores."""

    def __init__(self, *, rag, memory, session_search, sessions, max_context_chars: int = 12000):
        self.rag = rag
        self.memory = memory
        self.session_search = session_search
        self.sessions = sessions
        self.max_context_chars = max(500, max_context_chars)

    def plan(self, query: str, session_id: str | None = None, requested_mode: str = "mix") -> QueryPlan:
        original = " ".join(str(query or "").split())
        rewritten = self._rewrite(original, session_id)
        high = tuple(term for term in _GLOBAL_TERMS if term in rewritten)
        quoted = [item.strip() for item in _QUOTED.findall(rewritten) if item.strip()]
        ascii_terms = _ASCII_TERM.findall(rewritten)
        low = tuple(dict.fromkeys(quoted + ascii_terms))

        if requested_mode in {"precise", "global"}:
            rag_mode = requested_mode
        elif any(term in rewritten for term in _GLOBAL_TERMS):
            rag_mode = "global"
        elif any(term in rewritten for term in _PRECISE_TERMS):
            rag_mode = "precise"
        else:
            rag_mode = "mix"

        routes = ["document"]
        if rag_mode == "global" or any(term in rewritten for term in _RELATION_TERMS):
            routes.append("graph")
        routes.extend(("memory", "session"))
        return QueryPlan(original, rewritten, high, low, tuple(routes), rag_mode)

    def retrieve(
        self,
        query: str,
        session_id: str | None = None,
        collection_id: str | None = None,
        requested_mode: str = "mix",
    ) -> tuple[QueryPlan, list[UnifiedKnowledgeHit]]:
        plan = self.plan(query, session_id, requested_mode)
        hits: list[UnifiedKnowledgeHit] = []

        _, document_citations = self.rag.context_for(
            plan.rewritten_query,
            collection_id,
            plan.rag_mode,
        )
        for item in document_citations:
            hits.append(
                UnifiedKnowledgeHit(
                    "document",
                    str(item.get("chunk_id") or item.get("document_id") or ""),
                    str(item.get("title") or "知识库资料"),
                    str(item.get("content") or "").strip(),
                    float(item.get("score") or 0.0),
                    dict(item),
                )
            )

        query_tokens = tokenize(plan.rewritten_query)
        for entry in self.memory.list():
            score = self._token_score(query_tokens, entry.content)
            if score > 0:
                hits.append(
                    UnifiedKnowledgeHit(
                        "memory",
                        entry.id,
                        f"记忆·{entry.category}",
                        entry.content.strip(),
                        score,
                        {"category": entry.category, "source_session_id": entry.source_session_id},
                    )
                )

        for item in self.session_search.search(plan.rewritten_query):
            hits.append(
                UnifiedKnowledgeHit(
                    "session",
                    f"{item.session_id}:{item.role}",
                    item.session_name,
                    item.content.strip(),
                    min(1.0, float(item.score) / max(1, len(query_tokens))),
                    {"session_id": item.session_id, "role": item.role, "updated_at": item.updated_at},
                )
            )

        return plan, self._deduplicate(hits)

    def context_for(
        self,
        query: str,
        session_id: str | None = None,
        collection_id: str | None = None,
        requested_mode: str = "mix",
    ) -> tuple[str, list[dict[str, Any]]]:
        plan, hits = self.retrieve(query, session_id, collection_id, requested_mode)
        citations: list[dict[str, Any]] = []
        sections: list[str] = []
        used = 0
        for hit in hits:
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break
            content = hit.content[:remaining]
            if not content:
                continue
            index = len(citations) + 1
            citation = {
                "index": index,
                "source_type": hit.source_type,
                "source_id": hit.source_id,
                "title": hit.title,
                "content": content,
                "score": round(hit.score, 4),
                **hit.metadata,
            }
            citation["index"] = index
            citation["source_type"] = hit.source_type
            citations.append(citation)
            sections.append(f"[{index}] [{hit.source_type}] {hit.title}\n{content}")
            used += len(content)

        if not sections:
            return "", []
        high = "、".join(plan.high_level_keywords) or "无"
        low = "、".join(plan.low_level_keywords) or "无"
        header = (
            "[知识检索计划]\n"
            f"改写问题：{plan.rewritten_query}\n"
            f"检索路线：{'、'.join(plan.routes)}；图谱模式：{plan.rag_mode}\n"
            f"高层关键词：{high}；低层关键词：{low}"
        )
        return header + "\n\n[统一知识检索结果]\n" + "\n\n".join(sections) + "\n请用 [1]、[2] 标明引用来源。", citations

    def _rewrite(self, query: str, session_id: str | None) -> str:
        if not session_id or not any(term in query for term in _VAGUE_TERMS):
            return query
        try:
            messages: Iterable[Any] = self.sessions.get(session_id).messages
        except Exception:
            return query
        previous = next(
            (
                " ".join(str(message.content).split())
                for message in reversed(list(messages))
                if getattr(message, "role", None) == "user" and str(getattr(message, "content", "")).strip()
            ),
            "",
        )
        return f"{previous} {query}".strip() if previous and previous != query else query

    @staticmethod
    def _token_score(query_tokens: set[str], content: str) -> float:
        if not query_tokens:
            return 0.0
        return len(query_tokens & tokenize(content)) / len(query_tokens)

    @staticmethod
    def _deduplicate(hits: list[UnifiedKnowledgeHit]) -> list[UnifiedKnowledgeHit]:
        priority = {"document": 3, "memory": 2, "session": 1}
        best: dict[str, UnifiedKnowledgeHit] = {}
        for hit in hits:
            key = " ".join(hit.content.casefold().split())
            current = best.get(key)
            if current is None or (priority.get(hit.source_type, 0), hit.score) > (
                priority.get(current.source_type, 0),
                current.score,
            ):
                best[key] = hit
        return sorted(best.values(), key=lambda item: (-item.score, -priority.get(item.source_type, 0)))
