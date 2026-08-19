from __future__ import annotations

from pathlib import Path

import pytest

from iris_agent.attachments.errors import AttachmentNotFoundError, AttachmentStorageError
from iris_agent.attachments.storage import AttachmentStorage


def storage(root: Path) -> AttachmentStorage:
    return AttachmentStorage(root, max_file_bytes=100, max_total_bytes=200, max_count=2)


def test_saves_metadata_under_its_scope_and_opens_verified_content(tmp_path: Path) -> None:
    saved = storage(tmp_path).save("session-1", "notes.txt", b"safe", "text/plain")

    opened = storage(tmp_path).open("session-1", saved.id)

    assert saved.scope_id == "session-1"
    assert saved.extraction_status == "pending"
    assert opened.read_bytes() == b"safe"
    assert (tmp_path / "session-1" / "attachments" / "index.json").exists()


def test_opened_file_preserves_original_name_separately_from_storage_name(tmp_path: Path) -> None:
    target = storage(tmp_path)
    saved = target.save("session-1", "notes.txt", b"safe", "text/plain")

    opened = target.open("session-1", saved.id)

    assert opened.original_name == "notes.txt"
    assert opened.name != opened.original_name


def test_scope_cannot_read_or_delete_another_scope_attachment(tmp_path: Path) -> None:
    target = storage(tmp_path)
    saved = target.save("session-1", "notes.txt", b"safe", "text/plain")

    assert target.list("session-2") == []
    with pytest.raises(AttachmentNotFoundError):
        target.open("session-2", saved.id)
    with pytest.raises(AttachmentNotFoundError):
        target.delete("session-2", saved.id)


@pytest.mark.parametrize("scope_id", [".", ".."])
def test_scope_rejects_dot_segments(tmp_path: Path, scope_id: str) -> None:
    with pytest.raises(AttachmentStorageError):
        storage(tmp_path).list(scope_id)


def test_scope_rejects_preexisting_symlink(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    scope = tmp_path / "session-link"
    try:
        scope.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(AttachmentStorageError):
        storage(tmp_path).save("session-link", "notes.txt", b"safe", "text/plain")
