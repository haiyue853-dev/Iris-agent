from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

from iris_agent.documents import (
    DocumentExtraction,
    DocumentInvalidTypeError,
    DocumentNotFoundError,
    DocumentRepository,
    DocumentSource,
    DocumentService,
    DocumentStorageError,
    DocumentTooLargeError,
    DocumentTooManyError,
    DocumentTotalTooLargeError,
)


def repository(tmp_path: Path, **limits: int) -> DocumentRepository:
    return DocumentRepository(
        tmp_path,
        max_file_bytes=limits.get("max_file_bytes", 100),
        max_total_bytes=limits.get("max_total_bytes", 200),
        max_count=limits.get("max_count", 3),
        max_text_chars=limits.get("max_text_chars", 100),
    )


def text_result(text: str = "已提取的正文") -> DocumentExtraction:
    return DocumentExtraction(
        text=text,
        sources=(DocumentSource(file_name="notes.txt", location="正文"),),
        truncated=False,
    )


def test_save_normalizes_client_path_uses_uuid_and_keeps_body_out_of_metadata(tmp_path: Path) -> None:
    documents = repository(tmp_path)

    saved = documents.save("../../private/notes.txt", b"safe body", "text/plain")

    assert saved.original_name == "notes.txt"
    assert saved.suffix == ".txt"
    assert saved.extraction_status == "pending"
    assert len(saved.id) == 36
    assert documents.file_for(saved.id).name == "notes.txt"
    assert documents.file_for(saved.id).read_bytes() == b"safe body"
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert "safe body" not in json.dumps(index, ensure_ascii=False)
    assert "text" not in index["documents"][0]


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("notes.txt", "text/plain"),
        ("notes.md", "text/markdown"),
        ("notes.md", "text/plain"),
        ("notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("notes.pdf", "application/pdf"),
        ("notes.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("notes.xls", "application/vnd.ms-excel"),
    ],
)
def test_save_accepts_only_the_declared_extension_mime_pairs(tmp_path: Path, name: str, media_type: str) -> None:
    saved = repository(tmp_path).save(name, b"x", media_type)

    assert saved.original_name == name


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("notes.txt", "application/octet-stream"),
        ("notes.txt", "text/markdown"),
        ("notes.md", "application/pdf"),
        ("macro.docm", "application/vnd.ms-word.document.macroEnabled.12"),
        ("picture.png", "image/png"),
        ("notes.txt", ""),
    ],
)
def test_save_rejects_missing_unknown_or_mismatched_type_before_storing(tmp_path: Path, name: str, media_type: str) -> None:
    documents = repository(tmp_path)

    with pytest.raises(DocumentInvalidTypeError) as error:
        documents.save(name, b"x", media_type)

    assert error.value.code == "document_invalid_type"
    assert not list((tmp_path / "files").iterdir())


def test_save_rejects_too_large_count_and_total_quota(tmp_path: Path) -> None:
    with pytest.raises(DocumentTooLargeError) as too_large:
        repository(tmp_path, max_file_bytes=2).save("large.txt", b"123", "text/plain")
    assert too_large.value.code == "document_too_large"

    by_count = repository(tmp_path / "count", max_count=1)
    by_count.save("one.txt", b"1", "text/plain")
    with pytest.raises(DocumentTooManyError) as too_many:
        by_count.save("two.txt", b"1", "text/plain")
    assert too_many.value.code == "document_too_many"

    by_total = repository(tmp_path / "total", max_count=3, max_total_bytes=2)
    by_total.save("one.txt", b"12", "text/plain")
    with pytest.raises(DocumentTotalTooLargeError) as total_too_large:
        by_total.save("two.txt", b"3", "text/plain")
    assert total_too_large.value.code == "document_total_too_large"


def test_single_process_concurrent_saves_cannot_exceed_quota(tmp_path: Path) -> None:
    documents = repository(tmp_path, max_count=2, max_total_bytes=6)
    barrier = threading.Barrier(8)
    outcomes: list[str] = []

    def save() -> None:
        barrier.wait()
        try:
            documents.save("notes.txt", b"abc", "text/plain")
            outcomes.append("saved")
        except (DocumentTooManyError, DocumentTotalTooLargeError):
            outcomes.append("rejected")

    workers = [threading.Thread(target=save) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    saved = documents.list()
    assert len(saved) == 2
    assert sum(item.size_bytes for item in saved) == 6
    assert outcomes.count("saved") == 2


def test_ready_text_survives_restart_and_delete_removes_raw_text_and_metadata(tmp_path: Path) -> None:
    documents = repository(tmp_path)
    saved = documents.save("notes.txt", b"raw", "text/plain")
    ready = documents.update_extraction(saved.id, text_result("正文内容"))

    restarted = repository(tmp_path)

    assert restarted.list() == [ready]
    assert restarted.read_text(saved.id) == "正文内容"
    restarted.delete(saved.id)
    assert restarted.list() == []
    assert not (tmp_path / "files" / f"{saved.id}.txt").exists()
    assert not (tmp_path / "text" / f"{saved.id}.txt").exists()
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == {"documents": []}


def test_failed_extraction_is_persisted_without_body_and_can_still_be_deleted(tmp_path: Path) -> None:
    documents = repository(tmp_path)
    saved = documents.save("broken.pdf", b"not a pdf", "application/pdf")

    failed = documents.update_extraction(saved.id, None, message="无法提取文档文本")

    assert failed.extraction_status == "failed"
    assert failed.extraction_message == "无法提取文档文本"
    assert not (tmp_path / "text" / f"{saved.id}.txt").exists()
    restarted = repository(tmp_path)
    assert restarted.get(saved.id) == failed
    restarted.delete(saved.id)
    with pytest.raises(DocumentNotFoundError):
        restarted.get(saved.id)


def test_service_keeps_a_parse_failure_as_deletable_failed_document(tmp_path: Path) -> None:
    service = DocumentService(tmp_path)

    failed = service.upload("broken.pdf", b"not a pdf", "application/pdf")

    assert failed.extraction_status == "failed"
    assert failed.extraction_message == "无法提取文档文本"
    service.delete(failed.id)
    assert service.list() == []


def test_service_does_not_turn_storage_errors_into_parse_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = DocumentService(tmp_path)

    def fail_storage(_document: object) -> object:
        raise DocumentStorageError("无法访问文档存储")

    monkeypatch.setattr(service.extractor, "extract", fail_storage)

    with pytest.raises(DocumentStorageError):
        service.upload("notes.txt", b"body", "text/plain")


def _make_symlink(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")


def test_load_rejects_bad_index_and_file_symlink_without_reading_outside_storage(tmp_path: Path) -> None:
    directory = tmp_path / "files"
    directory.mkdir(parents=True)
    external = tmp_path / "outside.txt"
    external.write_text("outside", encoding="utf-8")
    document_id = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f"
    _make_symlink(directory / f"{document_id}.txt", external)
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "id": document_id,
                        "original_name": "safe.txt",
                        "suffix": ".txt",
                        "media_type": "text/plain",
                        "size_bytes": 7,
                        "created_at": 1.0,
                        "extraction_status": "pending",
                        "extraction_message": None,
                        "text_truncated": False,
                        "sources": [],
                        "file_name": f"{document_id}.txt",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DocumentStorageError) as error:
        repository(tmp_path)

    assert error.value.code == "document_storage_error"
    assert external.read_text(encoding="utf-8") == "outside"


def test_load_rejects_malformed_index_record(tmp_path: Path) -> None:
    (tmp_path / "index.json").write_text('{"documents": [{"id": "not-a-uuid"}]}', encoding="utf-8")

    with pytest.raises(DocumentStorageError):
        repository(tmp_path)
