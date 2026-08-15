import pytest

from iris_agent.core.models import Message
from iris_agent.session_search.service import SessionSearchService
from iris_agent.sessions.json_store import JsonSessionRepository


@pytest.fixture
def repository(tmp_path):
    return JsonSessionRepository(tmp_path)


def test_search_returns_ranked_hits(repository):
    s1 = repository.create("项目讨论")
    repository.append(s1.id, Message(role="user", content="聊聊项目进展"))
    search = SessionSearchService(repository)

    hits = search.search("项目进展")

    assert hits[0].session_id == s1.id
    assert hits[0].content == "聊聊项目进展"
    assert hits[0].score > 0


def test_search_skips_tool_messages_and_empty(repository):
    s1 = repository.create("空会话")
    repository.append(s1.id, Message(role="tool", content="机密参数"))
    repository.append(s1.id, Message(role="assistant", content="   "))
    search = SessionSearchService(repository)

    assert search.search("机密") == []
    assert search.search("") == []


def test_search_ranks_higher_score_first(repository):
    s1 = repository.create("会话一")
    repository.append(s1.id, Message(role="user", content="项目进展"))
    s2 = repository.create("会话二")
    repository.append(s2.id, Message(role="user", content="项目进展项目进展"))
    search = SessionSearchService(repository)

    hits = search.search("项目进展")

    assert hits[0].session_id == s2.id


def test_search_respects_limit(repository):
    s1 = repository.create("会话")
    for i in range(3):
        repository.append(s1.id, Message(role="user", content=f"项目进展 {i}"))
    search = SessionSearchService(repository)

    assert len(search.search("项目进展", limit=2)) == 2
