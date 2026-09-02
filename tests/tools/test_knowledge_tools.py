"""Knowledge tool tests: add_knowledge + search_knowledge."""

from __future__ import annotations

import pytest

from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService
from iris_agent.tools.builtin.knowledge_tools import build_add_knowledge_tool, build_search_knowledge_tool


@pytest.fixture
def service(tmp_path):
    repository = KnowledgeRepository(tmp_path)
    retriever = KeywordRetriever(repository.list, max_hit_chars=500)
    return KnowledgeService(repository, retriever)


def test_add_knowledge_tool_creates_review_draft_without_saving(service):
    tool = build_add_knowledge_tool(service)
    result = tool.invoke({"title": "多模态面试", "content": "多模态大模型结构"})
    assert result.ok
    assert result.value["__irisKind"] == "knowledge-draft"
    assert result.value["title"] == "多模态面试"
    assert result.value["category"] == "面经"
    assert result.value["source_url"] is None
    assert service.list() == []


def test_add_knowledge_tool_keeps_source_url_in_review_draft(service):
    tool = build_add_knowledge_tool(service)
    result = tool.invoke({"title": "面试", "content": "内容", "source_url": "https://x.com"})
    assert result.ok
    assert result.value["source_url"] == "https://x.com"


def test_add_knowledge_tool_requires_title(service):
    tool = build_add_knowledge_tool(service)
    result = tool.invoke({"content": "内容"})
    assert not result.ok


def test_search_knowledge_tool_returns_hits(service):
    service.add("多模态面试", "多模态大模型结构")
    tool = build_search_knowledge_tool(service)
    result = tool.invoke({"query": "多模态"})
    assert result.ok
    assert len(result.value["hits"]) == 1


def test_search_knowledge_tool_empty_for_no_match(service):
    tool = build_search_knowledge_tool(service)
    result = tool.invoke({"query": "完全不相关"})
    assert result.ok
    assert result.value["hits"] == []
