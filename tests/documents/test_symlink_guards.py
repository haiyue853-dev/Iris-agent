from __future__ import annotations

from pathlib import Path

import pytest

from iris_agent.documents import DocumentExtraction, DocumentRepository, DocumentSource, DocumentStorageError


def repository(tmp_path: Path) -> DocumentRepository:
    return DocumentRepository(
        tmp_path,
        max_file_bytes=100,
        max_total_bytes=200,
        max_count=3,
        max_text_chars=100,
    )


def ready_result() -> DocumentExtraction:
    return DocumentExtraction(
        text="正文",
        sources=(DocumentSource(file_name="notes.txt", location="正文"),),
        truncated=False,
    )


def mark_path_as_symlink(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    path_type = type(target)
    original = path_type.is_symlink

    def claimed_symlink(path: Path) -> bool:
        return path == target or original(path)

    monkeypatch.setattr(path_type, "is_symlink", claimed_symlink)


def fail_if_path_is_read(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    path_type = type(target)
    original = path_type.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == target:
            raise AssertionError("a claimed symlink must not be read")
        return original(path)

    monkeypatch.setattr(path_type, "read_bytes", guarded_read)


def test_mocked_root_symlink_is_rejected_before_loading_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_path_as_symlink(monkeypatch, tmp_path)

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)


def test_mocked_index_symlink_is_rejected_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    index = tmp_path / "index.json"
    mark_path_as_symlink(monkeypatch, index)
    fail_if_path_is_read(monkeypatch, index)

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)


def test_mocked_raw_symlink_is_rejected_before_the_raw_file_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")
    raw = tmp_path / "files" / f"{saved.id}.txt"
    mark_path_as_symlink(monkeypatch, raw)
    fail_if_path_is_read(monkeypatch, raw)

    with pytest.raises(DocumentStorageError):
        documents.file_for(saved.id)


def test_mocked_text_symlink_is_rejected_before_the_text_file_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")
    documents.update_extraction(saved.id, ready_result())
    text = tmp_path / "text" / f"{saved.id}.txt"
    mark_path_as_symlink(monkeypatch, text)
    fail_if_path_is_read(monkeypatch, text)

    with pytest.raises(DocumentStorageError):
        documents.read_text(saved.id)


def test_recovery_rejects_mocked_unregistered_raw_symlink_instead_of_following_or_deleting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    orphan = tmp_path / "files" / "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f.txt"
    orphan.write_bytes(b"outside target would be here")
    mark_path_as_symlink(monkeypatch, orphan)

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)
