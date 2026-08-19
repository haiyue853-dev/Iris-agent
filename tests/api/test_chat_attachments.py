from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from iris_agent.api.app import create_app
from iris_agent.attachments import AttachmentService, AttachmentStorage
from iris_agent.attachments.errors import AttachmentExtractError
from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.errors import SessionNotFoundError
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, schemas):
        return ProviderResponse(content="收到")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    attachments = AttachmentService(
        AttachmentStorage(tmp_path / "attachments", 100, 200, 2),
        sessions,
        LocalAttachmentExtractor(1000),
    )
    return TestClient(create_app(agent, sessions, chat_attachments=attachments)), sessions


def _session(client):
    return client.post("/api/sessions", json={"name": "chat"}).json()["id"]


def test_upload_list_download_and_delete_chat_attachment(tmp_path):
    client, _ = _client(tmp_path)
    session_id = _session(client)
    upload = client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("notes.txt", b"hello attachment", "text/plain")},
    )
    assert upload.status_code == 201
    item = upload.json()["attachment"]
    assert item["original_name"] == "notes.txt"
    assert item["extraction_status"] == "ready"
    assert client.get(f"/api/sessions/{session_id}/attachments").json()["attachments"] == [item]

    download = client.get(f"/api/sessions/{session_id}/attachments/{item['id']}/download")
    assert download.status_code == 200
    assert download.content == b"hello attachment"
    assert download.headers["content-type"].startswith("text/plain")
    assert "notes.txt" in download.headers["content-disposition"]
    assert str(tmp_path) not in download.text

    assert client.delete(f"/api/sessions/{session_id}/attachments/{item['id']}").status_code == 204
    assert client.get(f"/api/sessions/{session_id}/attachments").json()["attachments"] == []
    assert client.get(f"/api/sessions/{session_id}/attachments/{item['id']}/download").status_code == 404


def test_deleting_a_session_removes_its_chat_attachments(tmp_path):
    client, sessions = _client(tmp_path)
    session_id = _session(client)
    attachment_id = client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("notes.txt", b"hello attachment", "text/plain")},
    ).json()["attachment"]["id"]

    assert client.delete(f"/api/sessions/{session_id}").status_code == 204
    with pytest.raises(SessionNotFoundError):
        sessions.get(session_id)
    attachment_root = tmp_path / "attachments"
    assert attachment_id not in str(list(attachment_root.rglob("*")))


def test_startup_cleans_expired_unattached_chat_attachments(tmp_path, monkeypatch):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("chat")
    attachments = AttachmentService(
        AttachmentStorage(tmp_path / "attachments", 100, 200, 2),
        sessions,
        LocalAttachmentExtractor(1000),
    )
    attachments.upload(session.id, "expired.txt", b"expired", "text/plain")
    monkeypatch.setattr("iris_agent.attachments.storage.datetime", type("Clock", (), {
        "now": staticmethod(lambda timezone_arg: datetime.now(timezone.utc) + timedelta(days=2)),
        "fromisoformat": staticmethod(datetime.fromisoformat),
    }))
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")

    with TestClient(create_app(agent, sessions, chat_attachments=attachments)):
        pass

    assert attachments.list_for_session(session.id) == []


def test_upload_checks_session_and_streamed_size_limit(tmp_path):
    client, _ = _client(tmp_path)
    missing = client.post("/api/sessions/missing/attachments", files={"file": ("a.txt", b"ok", "text/plain")})
    assert missing.status_code == 404

    session_id = _session(client)
    oversized = client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("large.txt", b"x" * 101, "text/plain")},
    )
    assert oversized.status_code == 422
    assert oversized.json()["detail"]["code"] == "attachment_too_large"


def test_chat_stream_persists_attachment_ids_and_allows_attachment_only_message(tmp_path):
    client, sessions = _client(tmp_path)
    session_id = _session(client)
    attachment_id = client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("context.txt", b"context", "text/plain")},
    ).json()["attachment"]["id"]

    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "", "attachment_ids": [attachment_id]})
    assert response.status_code == 200
    assert sessions.get(session_id).messages[0].attachment_ids == [attachment_id]
    assert sessions.get(session_id).messages[0].content == ""

    invalid = client.post("/api/chat/stream", json={"session_id": session_id, "message": "", "attachment_ids": []})
    assert invalid.status_code == 422


def test_session_messages_restore_safe_attachment_metadata(tmp_path):
    client, _ = _client(tmp_path)
    session_id = _session(client)
    attachment = client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("context.txt", b"context", "text/plain")},
    ).json()["attachment"]

    assert client.post("/api/chat/stream", json={"session_id": session_id, "message": "请阅读", "attachment_ids": [attachment["id"]]}).status_code == 200
    message = client.get(f"/api/sessions/{session_id}").json()["messages"][0]

    assert message["attachment_ids"] == [attachment["id"]]
    assert message["attachments"] == [attachment]
    assert str(tmp_path) not in str(message)


def test_attachment_api_rejects_unknown_cross_session_and_path_ids(tmp_path):
    client, _ = _client(tmp_path)
    first_session = _session(client)
    second_session = _session(client)
    attachment_id = client.post(
        f"/api/sessions/{first_session}/attachments",
        files={"file": ("secret.txt", b"secret", "text/plain")},
    ).json()["attachment"]["id"]

    assert client.get(f"/api/sessions/{first_session}/attachments/missing/download").status_code == 404
    assert client.get(f"/api/sessions/{second_session}/attachments/{attachment_id}/download").status_code == 422
    for attachment_id in ("..", "C:/workspace/secret.txt"):
        response = client.post(
            "/api/chat/stream",
            json={"session_id": second_session, "message": "read", "attachment_ids": [attachment_id]},
        )
        assert response.status_code in {404, 422}
        assert str(tmp_path) not in response.text


def test_upload_extraction_failure_returns_safe_metadata(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    monkeypatch.setattr(
        LocalAttachmentExtractor,
        "extract",
        lambda *_: (_ for _ in ()).throw(AttachmentExtractError(f"failed at {tmp_path}")),
    )

    response = client.post(
        f"/api/sessions/{_session(client)}/attachments",
        files={"file": ("broken.txt", b"text", "text/plain")},
    )

    assert response.status_code == 201
    attachment = response.json()["attachment"]
    assert attachment["extraction_status"] == "failed"
    assert attachment["extraction_message"] == "无法提取附件文本"
    assert str(tmp_path) not in response.text


def test_stream_provider_failure_returns_safe_error_and_keeps_session_usable(tmp_path):
    class FailingProvider:
        def complete(self, messages, schemas):
            raise RuntimeError(f"provider failed at {tmp_path}")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(FailingProvider(), ToolRegistry()), sessions, "system")
    client = TestClient(create_app(agent, sessions))
    session_id = _session(client)

    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "hello"})

    assert response.status_code == 200
    assert '"code": "internal_error"' in response.text
    assert str(tmp_path) not in response.text
    assert client.get(f"/api/sessions/{session_id}").status_code == 200
