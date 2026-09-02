"""SQLite-backed persistence tests for RAG documents."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from iris_agent.knowledge.chunker import ChunkDraft, ChunkGroup
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


def test_chunk_edit_preserves_id_updates_fts_and_records_restorable_revision(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft("oldalpha", "第 2 页")])
    original = repository.chunks_for_document(document.id)[0]

    updated = repository.update_chunk(original.id, "newomega", "第 3 页")
    revisions = repository.chunk_revisions(original.id)

    assert updated.id == original.id
    assert updated.content == "newomega"
    assert repository.keyword_search("newomega", 5)[0].chunk_id == original.id
    assert repository.keyword_search("oldalpha", 5) == []
    assert revisions[0]["content"] == "oldalpha"
    restored = repository.restore_chunk_revision(original.id, revisions[0]["id"])
    assert restored.id == original.id
    assert restored.content == "oldalpha"
    assert repository.keyword_search("oldalpha", 5)[0].chunk_id == original.id


def test_parent_child_chunks_retrieve_leaf_and_expand_to_parent(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkGroup(
        parent=ChunkDraft("父级背景：向量数据库。具体事实：sqlite-vec 支持本地近邻搜索。", "第 3 页"),
        children=(
            ChunkDraft("父级背景：向量数据库。", "第 3 页"),
            ChunkDraft("具体事实：sqlite-vec 支持本地近邻搜索。", "第 3 页"),
        ),
    )])

    chunks = repository.chunks_for_document(document.id)
    parent = next(chunk for chunk in chunks if chunk.parent_id is None)
    children = [chunk for chunk in chunks if chunk.parent_id == parent.id]
    hits = repository.keyword_search("sqlite vec", 5)

    assert hits
    assert {hit.chunk_id for hit in hits} <= {chunk.id for chunk in children}
    assert repository.parent_context_for([hits[0].chunk_id])[hits[0].chunk_id] == parent


def test_sqlite_vec_embedding_search_returns_nearest_leaf_chunk(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [
        ChunkDraft("数据库检索", None),
        ChunkDraft("前端主题", None),
    ])
    chunks = repository.chunks_for_document(document.id)
    repository.save_embeddings(document.id, "bge-m3", {
        chunks[0].id: [1.0, 0.0, 0.0],
        chunks[1].id: [0.0, 1.0, 0.0],
    })

    hits = repository.embedding_search([0.99, 0.01, 0.0], 1)

    assert hits[0].chunk_id == chunks[0].id
    assert hits[0].similarity > 0.99


def test_embedding_search_falls_back_when_sqlite_vec_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("iris_agent.knowledge.sqlite_repository._sqlite_vec", None)
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [
        ChunkDraft("数据库检索", None),
        ChunkDraft("前端主题", None),
    ])
    chunks = repository.chunks_for_document(document.id)
    repository.save_embeddings(document.id, "bge-m3", {
        chunks[0].id: [1.0, 0.0, 0.0],
        chunks[1].id: [0.0, 1.0, 0.0],
    })

    hits = repository.embedding_search([0.99, 0.01, 0.0], 1)

    assert [hit.chunk_id for hit in hits] == [chunks[0].id]
    assert hits[0].similarity > 0.99


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


def test_keyword_search_matches_relevant_terms_in_natural_question(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft("注意力机制用于计算上下文关系", None)])

    hits = repository.keyword_search("什么是注意力机制", 5)

    assert hits and hits[0].document_id == document.id


def test_embedding_candidates_do_not_silently_drop_chunks_after_200(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft(f"chunk {index}", None) for index in range(201)])
    chunks = repository.chunks_for_document(document.id)
    repository.save_embeddings(document.id, "bge-m3", {chunk.id: [float(index), 1.0] for index, chunk in enumerate(chunks)})

    candidates = repository.embedding_candidates()

    assert len(candidates) == 201


def test_graph_storage_merges_case_variants_without_node_id_collision(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft("RAG and rag", None)])
    chunk = repository.chunks_for_document(document.id)[0]

    repository.replace_document_graph(
        document.id,
        [("RAG", "topic"), ("rag", "entity")],
        [("RAG", "rag", "别名", chunk.id, 0.8)],
    )

    connection = sqlite3.connect(tmp_path / "knowledge.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0] == 0
    finally:
        connection.close()


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


def test_collection_retrieval_config_persists_after_database_reopen(tmp_path):
    db_path = tmp_path / "knowledge.db"
    repository = SqliteKnowledgeRepository(db_path)
    collection = repository.create_collection("项目资料")

    updated = repository.update_collection_retrieval_config(collection.id, {
        "top_k": 3,
        "candidate_multiplier": 5,
        "minimum_relevance_score": 0.35,
        "mmr_relevance_weight": 0.6,
    })

    assert updated.retrieval_config == {
        "top_k": 3,
        "candidate_multiplier": 5,
        "minimum_relevance_score": 0.35,
        "mmr_relevance_weight": 0.6,
    }
    reopened = next(item for item in SqliteKnowledgeRepository(db_path).list_collections() if item.id == collection.id)
    assert reopened.retrieval_config == updated.retrieval_config


def test_existing_collection_schema_gains_retrieval_config_on_repository_open(tmp_path):
    db_path = tmp_path / "knowledge.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE knowledge_collections (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, created_at REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO knowledge_collections (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            ("collection-general", "通用资料", None, 1.0),
        )

    repository = SqliteKnowledgeRepository(db_path)

    assert repository.collection_retrieval_config("collection-general") == {}
