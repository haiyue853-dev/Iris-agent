from datetime import datetime, timedelta, timezone
import json

import pytest

from iris_agent.attachments import AttachmentAccessError, AttachmentMetadata, AttachmentReference, AttachmentStorage
from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.service import AttachmentService
from iris_agent.sessions.json_store import JsonSessionRepository


@pytest.fixture
def session_repo(tmp_path):
    repository = JsonSessionRepository(tmp_path / "sessions")
    repository.create("会话 A")
    repository.create("会话 B")
    sessions = repository.list()
    return repository, sessions[0], sessions[1]


@pytest.fixture
def attachment_service(tmp_path, session_repo):
    repository, _, _ = session_repo
    return AttachmentService(
        AttachmentStorage(tmp_path / "attachments", 100, 200, 5, temporary_ttl=timedelta(seconds=1)),
        repository,
        LocalAttachmentExtractor(max_chars=4),
    )


def test_attachment_reference_json_round_trip():
    reference = AttachmentReference(id="a1", original_name="notes.txt", sources=("page:1",))
    assert AttachmentReference.from_dict(reference.to_dict()) == reference
    assert reference.to_dict() == {"id": "a1", "original_name": "notes.txt", "sources": ["page:1"]}


@pytest.mark.parametrize("payload", [{}, {"id": "", "original_name": "x", "sources": []}, {"id": "a", "original_name": "x", "sources": [1]}, {"id": "a", "original_name": "x", "sources": ("page:1",)}])
def test_attachment_reference_rejects_invalid_data(payload):
    with pytest.raises(ValueError):
        AttachmentReference.from_dict(payload)


def test_attachment_metadata_is_frozen_and_validates_basics():
    metadata = AttachmentMetadata(
        id="a1", scope_id="session-1", original_name="notes.txt", media_type="text/plain",
        size_bytes=3, created_at=datetime.now(timezone.utc), extraction_status="ready",
        extraction_message=None, text_truncated=False, sources=("text:1",),
    )
    with pytest.raises((AttributeError, TypeError)):
        metadata.id = "a2"


def test_upload_extracts_text_and_attach_persists_only_the_reference(attachment_service, session_repo):
    repository, session_a, _ = session_repo
    uploaded = attachment_service.upload(session_a.id, "notes.txt", b"hello", "text/plain")

    attached = attachment_service.attach_to_session(session_a.id, [uploaded.id])
    message = repository.get(session_a.id).messages[-1]

    assert uploaded.extraction_status == "ready"
    assert uploaded.extracted_text == "hell"
    assert uploaded.text_truncated is True
    assert attached == [uploaded]
    assert message.attachment_ids == [uploaded.id]
    assert "hello" not in json.dumps({"content": message.content, "attachment_ids": message.attachment_ids})


def test_session_cannot_read_download_or_detach_another_sessions_attachment(attachment_service, session_repo):
    _, session_a, session_b = session_repo
    uploaded = attachment_service.upload(session_a.id, "notes.txt", b"secret", "text/plain")

    for operation in (
        lambda: attachment_service.read(session_b.id, uploaded.id),
        lambda: attachment_service.download_path(session_b.id, uploaded.id),
        lambda: attachment_service.detach_from_session(session_b.id, uploaded.id),
    ):
        with pytest.raises(AttachmentAccessError):
            operation()


def test_detach_deletes_attachment_and_removes_message_reference(attachment_service, session_repo):
    repository, session_a, _ = session_repo
    uploaded = attachment_service.upload(session_a.id, "notes.txt", b"hello", "text/plain")
    attachment_service.attach_to_session(session_a.id, [uploaded.id])

    attachment_service.detach_from_session(session_a.id, uploaded.id)

    assert repository.get(session_a.id).messages[-1].attachment_ids == []
    assert attachment_service.list_for_session(session_a.id) == []


def test_cleanup_removes_only_expired_unattached_files(attachment_service, session_repo, monkeypatch):
    _, session_a, _ = session_repo
    temporary = attachment_service.upload(session_a.id, "temporary.txt", b"temporary", "text/plain")
    attached = attachment_service.upload(session_a.id, "attached.txt", b"attached", "text/plain")
    attachment_service.attach_to_session(session_a.id, [attached.id])

    monkeypatch.setattr("iris_agent.attachments.storage.datetime", type("Clock", (), {
        "now": staticmethod(lambda timezone_arg: datetime.now(timezone.utc) + timedelta(seconds=2)),
        "fromisoformat": staticmethod(datetime.fromisoformat),
    }))
    attachment_service.cleanup_expired()

    assert [item.id for item in attachment_service.list_for_session(session_a.id)] == [attached.id]
    assert temporary.id != attached.id
