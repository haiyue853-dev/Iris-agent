"""SQLite-backed persistence tests for RAG documents."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from iris_agent.knowledge.chunker import ChunkDraft
from iris_agent.knowledge.documents import KnowledgeChunk, KnowledgeDocument
from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository, SqliteKnowledgeRepositoryError


def _document(**overrides) -> KnowledgeDocument:
    fields = {
        "id": "doc-0123456789abcdef0123456789abcdef",
        "title": "Transformer 面经.pdf",
        "source_type": "upload",
        "media_type": "application/pdf",
        "size_bytes": 42,
        "original_name": "transformer.pdf",
        "status": "ready",
        "error_message": None,
        "created_at": 1000.0,
        "updated_at": 1000.0,
    }
    fields.update(overrides)
    return KnowledgeDocument(**fields)


def test_save_document_indexes_chunks_and_cascades_delete(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft("Transformer 注意力机制", "第 2 页")])

    hit = repository.keyword_search("注意力", 5)[0]
    assert hit.document_id == document.id
    assert hit.title == document.title
    assert hit.content == "Transformer 注意力机制"
    assert hit.location == "第 2 页"

    deleted = repository.delete_document(document.id)
    assert deleted is not None
    assert deleted.original_name == "transformer.pdf"
    assert repository.keyword_search("注意力", 5) == []
    assert repository.embedding_count(document.id) == 0


def test_failed_save_rolls_back_document_chunks_and_fts(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    chunks = [
        KnowledgeChunk.new(document.id, 0, "first chunk"),
        KnowledgeChunk.new(document.id, 0, "duplicate ordinal"),
    ]

    with pytest.raises(SqliteKnowledgeRepositoryError):
        repository.save_document_with_chunks(document, chunks)

    assert repository.get_document(document.id) is None
    assert repository.keyword_search("first", 5) == []


def test_save_embeddings_replaces_vectors_and_counts_document_chunks(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    chunks = [ChunkDraft("one", None), ChunkDraft("two", None)]
    repository.save_document_with_chunks(document, chunks)
    chunk_ids = [row[0] for row in sqlite3.connect(tmp_path / "knowledge.db").execute("SELECT id FROM chunks ORDER BY ordinal")]

    repository.save_embeddings(document.id, "bge-m3", {chunk_ids[0]: [0.1, 0.2], chunk_ids[1]: [0.3, 0.4]})
    repository.save_embeddings(document.id, "bge-m3", {chunk_ids[0]: [0.5, 0.6]})

    assert repository.embedding_count(document.id) == 2


def test_json_migration_is_idempotent_and_preserves_legacy_files(tmp_path):
    legacy = KnowledgeRepository(tmp_path / "legacy")
    entry = KnowledgeEntry(
        id="kb-0123456789ab", title="旧条目", content="旧正文，包含注意力机制", category="面经",
        source_url="https://example.com/legacy", source_type="scrape", created_at=3.0, updated_at=4.0,
    )
    legacy.save(entry)
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")

    assert repository.migrate_legacy(legacy) == 1
    assert repository.migrate_legacy(legacy) == 0
    assert legacy.get(entry.id) == entry
    hit = repository.keyword_search("注意力", 5)[0]
    assert hit.title == entry.title
    migrated_document = repository.get_document(hit.document_id)
    assert migrated_document.source_type == "scrape"
    assert entry.source_url in migrated_document.original_name


def test_legacy_migration_uses_stable_id_when_source_url_changes(tmp_path):
    legacy = KnowledgeRepository(tmp_path / "legacy")
    entry = KnowledgeEntry(
        id="kb-0123456789ab", title="旧条目", content="旧正文", category="面经",
        source_url="https://example.com/one", source_type="scrape", created_at=3.0, updated_at=4.0,
    )
    legacy.save(entry)
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    assert repository.migrate_legacy(legacy) == 1

    legacy.save(KnowledgeEntry(
        id=entry.id, title=entry.title, content=entry.content, category=entry.category,
        source_url="https://example.com/two", source_type=entry.source_type,
        created_at=entry.created_at, updated_at=5.0,
    ))

    assert repository.migrate_legacy(legacy) == 0


def test_concurrent_legacy_migration_is_idempotent(tmp_path):
    legacy = KnowledgeRepository(tmp_path / "legacy")
    legacy.save(KnowledgeEntry(
        id="kb-0123456789ab", title="旧条目", content="旧正文", category="面经",
        source_url=None, source_type="manual", created_at=3.0, updated_at=4.0,
    ))
    db_path = tmp_path / "knowledge.db"
    first = SqliteKnowledgeRepository(db_path)
    second = SqliteKnowledgeRepository(db_path)
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[Exception] = []

    def migrate(repository):
        try:
            barrier.wait()
            results.append(repository.migrate_legacy(legacy))
        except Exception as exc:  # The regression is a database UNIQUE error.
            errors.append(exc)

    threads = [threading.Thread(target=migrate, args=(repository,)) for repository in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(results) == [0, 1]
    assert len(first.list_documents()) == 1


def test_database_reopens_and_retains_search_index(tmp_path):
    db_path = tmp_path / "knowledge.db"
    document = _document()
    SqliteKnowledgeRepository(db_path).save_document_with_chunks(document, [ChunkDraft("可重开检索", None)])

    assert SqliteKnowledgeRepository(db_path).keyword_search("重开", 1)[0].document_id == document.id


@pytest.mark.parametrize("document_id", ["../doc", "doc-not-hex", "", None])
def test_rejects_invalid_document_ids(tmp_path, document_id):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    with pytest.raises(ValueError):
        repository.get_document(document_id)


@pytest.mark.parametrize("query, limit", [("", 1), ("  ", 1), ("valid", 0), ("valid", -1), ("valid", True)])
def test_rejects_invalid_search_text_or_limit(tmp_path, query, limit):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    with pytest.raises(ValueError):
        repository.keyword_search(query, limit)
