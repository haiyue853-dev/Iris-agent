from __future__ import annotations

import multiprocessing

import pytest

from iris_agent.knowledge.chunker import chunk_text
from iris_agent.knowledge.documents import KnowledgeChunk, KnowledgeDocument


def _chunk_in_child(results, text: str) -> None:
    chunks = chunk_text(text, location="第 9 页", target_chars=800, overlap_chars=120)
    results.put([(chunk.content, chunk.location) for chunk in chunks])


def test_chunker_preserves_chinese_text_overlap_and_location():
    chunks = chunk_text("甲。" * 700, location="第 3 页", target_chars=800, overlap_chars=120)

    assert len(chunks) >= 2
    assert all(chunk.location == "第 3 页" for chunk in chunks)
    assert chunks[0].content[-100:] in chunks[1].content
    assert "".join(chunk.content for chunk in chunks).replace(chunks[0].content[-120:], "", 1).count("甲。") >= 700


def test_chunker_returns_no_drafts_for_whitespace():
    assert chunk_text(" \n\t ", location=None, target_chars=800, overlap_chars=120) == []


def test_chunker_hard_splits_oversized_unbroken_text_without_losing_content():
    text = "甲" * 1601
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    process = context.Process(target=_chunk_in_child, args=(results, text))
    process.start()
    process.join(timeout=2)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("chunk_text did not return for an oversized unbroken paragraph")

    chunks = results.get(timeout=1)
    assert process.exitcode == 0
    assert len(chunks) == 3
    assert all(len(content) <= 800 and location == "第 9 页" for content, location in chunks)
    assert chunks[0][0] + "".join(content[120:] for content, _ in chunks[1:]) == text


def test_chunker_rejects_invalid_limits():
    with pytest.raises(ValueError):
        chunk_text("正文", location=None, target_chars=0, overlap_chars=0)
    with pytest.raises(ValueError):
        chunk_text("正文", location=None, target_chars=10, overlap_chars=10)


def test_document_and_chunk_round_trip_through_safe_dicts():
    document = KnowledgeDocument.new(
        "资料.pdf", source_type="upload", media_type="application/pdf", size_bytes=42, original_name="资料.pdf"
    )
    chunk = KnowledgeChunk.new(document.id, 0, "这是切片正文。", location="第 1 页")

    assert KnowledgeDocument.from_dict(document.to_dict()) == document
    assert KnowledgeChunk.from_dict(chunk.to_dict()) == chunk


@pytest.mark.parametrize(
    "factory",
    [
        lambda: KnowledgeDocument.new(" ", source_type="manual"),
        lambda: KnowledgeDocument.new("标题", source_type="invalid"),
        lambda: KnowledgeDocument.new("标题", source_type="manual", size_bytes=-1),
        lambda: KnowledgeDocument(
            id="not-a-document", title="标题", source_type="manual", media_type=None, size_bytes=0,
            original_name=None, status="ready", error_message=None, created_at=1.0, updated_at=1.0,
        ),
        lambda: KnowledgeDocument(
            id="doc-0123456789abcdef0123456789abcdef", title="标题", source_type="manual", media_type=None,
            size_bytes=0, original_name=None, status="unknown", error_message=None, created_at=1.0, updated_at=1.0,
        ),
        lambda: KnowledgeChunk.new("doc-0123456789abcdef0123456789abcdef", 0, " "),
    ],
)
def test_document_models_reject_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
