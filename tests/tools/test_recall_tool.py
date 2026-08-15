import pytest

from iris_agent.core.models import Message
from iris_agent.session_search.service import SessionSearchService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.builtin.recall_tool import build_recall_tool
from iris_agent.tools.registry import ToolRegistry


@pytest.fixture
def search(tmp_path):
    repository = JsonSessionRepository(tmp_path)
    session = repository.create("项目讨论")
    repository.append(session.id, Message(role="user", content="聊聊项目进展"))
    return SessionSearchService(repository)


def test_recall_tool_returns_hits(search):
    tool = build_recall_tool(search)

    result = tool.invoke({"query": "项目进展"})

    assert result.ok
    assert isinstance(result.value["hits"], list)
    assert result.value["hits"][0]["content"] == "聊聊项目进展"


def test_recall_tool_returns_empty_for_no_match(search):
    tool = build_recall_tool(search)

    result = tool.invoke({"query": "完全不相关的词"})

    assert result.ok
    assert result.value["hits"] == []


def test_recall_tool_requires_query(search):
    registry = ToolRegistry()
    registry.register(build_recall_tool(search))

    result = registry.invoke("recall", {})

    assert not result.ok
    assert result.error_code == "invalid_tool_arguments"
