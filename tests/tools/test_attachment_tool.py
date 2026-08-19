from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.service import AttachmentService
from iris_agent.attachments.storage import AttachmentStorage
from iris_agent.core.models import Message
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.builtin.attachments import build_read_attachment_tool


def _service(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    sessions.create("one")
    sessions.create("two")
    service = AttachmentService(AttachmentStorage(tmp_path / "files", 10000, 10000, 5), sessions, LocalAttachmentExtractor(1000))
    return service, sessions


def test_read_attachment_returns_text_metadata_and_sources(tmp_path):
    service, sessions = _service(tmp_path)
    session = sessions.list()[0]
    item = service.upload(session.id, "notes.txt", b"hello", "text/plain")
    tool = build_read_attachment_tool(service, session.id)

    result = tool.invoke({"attachment_id": item.id, "max_chars": 3})

    assert result.ok
    assert result.value == {"name": "notes.txt", "text": "hel", "truncated": True, "sources": ["notes.txt"]}


def test_read_attachment_cannot_cross_session_or_accept_path(tmp_path):
    service, sessions = _service(tmp_path)
    first, second = sessions.list()
    item = service.upload(first.id, "notes.txt", b"secret", "text/plain")
    tool = build_read_attachment_tool(service, second.id)

    denied = tool.invoke({"attachment_id": item.id})
    path = tool.invoke({"attachment_id": "../" + item.id})

    assert not denied.ok and denied.error_code in {"attachment_access_denied", "attachment_not_found"}
    assert not path.ok and path.error_code == "invalid_attachment_id"
