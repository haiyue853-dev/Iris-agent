import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from iris_agent.core.errors import SessionNotFoundError
from iris_agent.core.models import Message
from iris_agent.sessions.json_store import JsonSessionRepository


def test_session_crud_survives_repository_restart(tmp_path):
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("测试")
    repo.append(session.id, Message(role="user", content="你好"))
    assert JsonSessionRepository(tmp_path).get(session.id).messages[0].content == "你好"
    repo.clear(session.id)
    assert repo.get(session.id).messages == []
    repo.delete(session.id)
    with pytest.raises(SessionNotFoundError):
        repo.get(session.id)


def test_corrupt_session_is_skipped(tmp_path):
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert JsonSessionRepository(tmp_path).list() == []


def test_reads_legacy_session_and_meta_files(tmp_path):
    (tmp_path / "session_1.json").write_text(json.dumps([{"role": "user", "content": "旧消息"}]), encoding="utf-8")
    (tmp_path / "session_1_meta.json").write_text(json.dumps({"id": "session_1", "name": "旧会话", "created_at": 1, "updated_at": 2}), encoding="utf-8")
    session = JsonSessionRepository(tmp_path).get("session_1")
    assert session.name == "旧会话"
    assert session.messages[0].content == "旧消息"


def test_session_id_cannot_escape_storage(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    with pytest.raises(SessionNotFoundError):
        repo.get("../outside")


def test_concurrent_appends_do_not_lose_messages(tmp_path):
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("并发")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: repo.append(session.id, Message(role="user", content=str(i))), range(20)))
    assert len(repo.get(session.id).messages) == 20


def test_message_attachment_ids_survive_restart_and_old_records_default_to_empty(tmp_path):
    repo = JsonSessionRepository(tmp_path)
    session = repo.create("附件")
    repo.append(session.id, Message(role="user", content="请阅读", attachment_ids=["attachment-1"]))

    assert JsonSessionRepository(tmp_path).get(session.id).messages[0].attachment_ids == ["attachment-1"]

    payload = json.loads((tmp_path / f"{session.id}.json").read_text(encoding="utf-8"))
    del payload["messages"][0]["attachment_ids"]
    (tmp_path / f"{session.id}.json").write_text(json.dumps(payload), encoding="utf-8")
    assert JsonSessionRepository(tmp_path).get(session.id).messages[0].attachment_ids == []
