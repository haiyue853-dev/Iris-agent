from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from iris_agent.documents import (
    DocumentExtractFailedError,
    DocumentExtraction,
    DocumentRepository,
    DocumentSource,
    DocumentStorageError,
)


def repository(tmp_path: Path) -> DocumentRepository:
    return DocumentRepository(
        tmp_path,
        max_file_bytes=100,
        max_total_bytes=200,
        max_count=3,
        max_text_chars=100,
    )


def ready_result(name: str = "notes.txt") -> DocumentExtraction:
    return DocumentExtraction(
        text="已经登记的正文",
        sources=(DocumentSource(file_name=name, location="正文"),),
        truncated=False,
    )


def test_restart_recovers_raw_left_by_crash_before_index_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = repository(tmp_path)

    def simulate_process_termination() -> None:
        raise SystemExit("simulated crash")

    monkeypatch.setattr(documents, "_write_index", simulate_process_termination)

    with pytest.raises(SystemExit):
        documents.save("lost.txt", b"raw left behind", "text/plain")

    restarted = repository(tmp_path)

    assert restarted.list() == []
    assert list((tmp_path / "files").iterdir()) == []


def test_restart_recovers_raw_and_text_left_by_crash_after_delete_index_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")
    documents.update_extraction(saved.id, ready_result())

    def simulate_process_termination(*_args: object, **_kwargs: object) -> None:
        raise SystemExit("simulated crash")

    monkeypatch.setattr(documents, "_unlink_controlled", simulate_process_termination)

    with pytest.raises(SystemExit):
        documents.delete(saved.id)

    restarted = repository(tmp_path)

    assert restarted.list() == []
    assert list((tmp_path / "files").iterdir()) == []
    assert list((tmp_path / "text").iterdir()) == []


def test_restart_cleans_only_unregistered_server_named_orphans_and_preserves_registered_data(
    tmp_path: Path,
) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"registered raw", "text/plain")
    documents.update_extraction(saved.id, ready_result())
    orphan_id = uuid4()
    raw_orphan = tmp_path / "files" / f"{orphan_id}.txt"
    text_orphan = tmp_path / "text" / f"{orphan_id}.txt"
    raw_orphan.write_bytes(b"interrupted raw")
    text_orphan.write_text("interrupted text", encoding="utf-8")
    (tmp_path / f".iris-document-{uuid4().hex}.tmp").write_bytes(b"temporary index write")

    restarted = repository(tmp_path)

    assert restarted.get(saved.id).extraction_status == "ready"
    assert restarted.file_for(saved.id).read_bytes() == b"registered raw"
    assert restarted.read_text(saved.id) == "已经登记的正文"
    assert not raw_orphan.exists()
    assert not text_orphan.exists()
    assert not list(tmp_path.glob(".iris-document-*.tmp"))


def test_restart_cleans_fixed_internal_temporary_files_from_every_controlled_directory(tmp_path: Path) -> None:
    documents = repository(tmp_path)
    temporary_paths = [
        directory / f".iris-document-{uuid4().hex}.tmp"
        for directory in (tmp_path, tmp_path / "files", tmp_path / "text")
    ]
    for temporary in temporary_paths:
        temporary.write_bytes(b"interrupted atomic write")

    restarted = repository(tmp_path)

    assert restarted.list() == []
    assert all(not temporary.exists() for temporary in temporary_paths)


def test_restart_still_rejects_unknown_residue_even_when_index_is_valid(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "files" / "manual-upload.txt").write_bytes(b"unknown")

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)


def test_restart_marks_pending_document_failed_after_interrupted_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")

    def simulate_process_termination() -> None:
        raise SystemExit("simulated crash")

    monkeypatch.setattr(documents, "_write_index", simulate_process_termination)

    with pytest.raises(SystemExit):
        documents.update_extraction(saved.id, ready_result())

    restarted = repository(tmp_path)

    recovered = restarted.get(saved.id)
    assert recovered.extraction_status == "failed"
    assert recovered.extraction_message == "文档提取在服务中断后未完成"
    assert restarted.file_for(saved.id).read_bytes() == b"raw"
    with pytest.raises(DocumentExtractFailedError):
        restarted.read_text(saved.id)
    assert list((tmp_path / "text").iterdir()) == []


def test_restart_keeps_rejecting_missing_registered_raw_file(tmp_path: Path) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")
    (tmp_path / "files" / f"{saved.id}.txt").unlink()

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)
