"""Transactional SQLite persistence for local RAG documents."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias
from uuid import uuid4

from iris_agent.knowledge.chunker import ChunkDraft, ChunkGroup
from iris_agent.knowledge.collections import KnowledgeCollection, normalise_retrieval_config
from iris_agent.knowledge.documents import KnowledgeChunk, KnowledgeDocument
from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.mindmap import MindMapNode
from iris_agent.knowledge.repository import KnowledgeRepository

try:
    import sqlite_vec as _sqlite_vec
except ImportError:
    _sqlite_vec = None


class SqliteKnowledgeRepositoryError(RuntimeError):
    """A RAG document operation could not be safely completed."""


@dataclass(frozen=True, slots=True)
class KeywordSearchHit:
    """A keyword match at chunk granularity."""

    chunk_id: str
    document_id: str
    title: str
    content: str
    location: str | None
    score: float


@dataclass(frozen=True, slots=True)
class EmbeddingSearchHit:
    """A vector ANN match at chunk granularity."""

    chunk_id: str
    document_id: str
    title: str
    content: str
    location: str | None
    similarity: float


@dataclass(frozen=True, slots=True)
class EmbeddingSearchCandidate:
    chunk_id: str
    document_id: str
    title: str
    content: str
    location: str | None
    vector: list[float]


@dataclass(frozen=True, slots=True)
class KnowledgeGraphNode:
    id: str
    label: str
    kind: str
    document_count: int


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEdge:
    source: str
    target: str
    relation: str
    document_id: str
    evidence_chunk_id: str | None = None
    confidence: float = 1.0
    evidence: str | None = None


EmbeddingMappings: TypeAlias = Mapping[str, Sequence[float]] | Iterable[tuple[str, Sequence[float]]]


class SqliteKnowledgeRepository:
    """Stores documents, searchable chunks and their vectors in one SQLite database."""

    def __init__(self, db_path: Path):
        if not isinstance(db_path, Path):
            raise ValueError("database path must be a Path")
        self.db_path = db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        media_type TEXT,
                        size_bytes INTEGER NOT NULL,
                        original_name TEXT,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS chunks (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        location TEXT,
                        content_hash TEXT NOT NULL,
                        parent_id TEXT REFERENCES chunks(id) ON DELETE CASCADE,
                        UNIQUE(document_id, ordinal)
                    );
                    CREATE TABLE IF NOT EXISTS chunk_embeddings (
                        chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                        model TEXT NOT NULL,
                        dimensions INTEGER NOT NULL,
                        vector_json TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS chunk_revisions (
                        id TEXT PRIMARY KEY,
                        chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                        content TEXT NOT NULL,
                        location TEXT,
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS chunk_revisions_chunk_idx ON chunk_revisions(chunk_id, created_at DESC);
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                    USING fts5(chunk_id UNINDEXED, title, content);
                    CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
                    CREATE TABLE IF NOT EXISTS graph_nodes (
                        id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE, kind TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS graph_edges (
                        source_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                        target_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        evidence_chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
                        confidence REAL NOT NULL DEFAULT 1.0,
                        UNIQUE(source_id, target_id, relation, document_id, evidence_chunk_id)
                    );
                    CREATE INDEX IF NOT EXISTS graph_edges_document_idx ON graph_edges(document_id);
                    CREATE TABLE IF NOT EXISTS document_mindmap_nodes (
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        node_id TEXT NOT NULL,
                        parent_id TEXT,
                        label TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        ordinal INTEGER NOT NULL,
                        evidence_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
                        PRIMARY KEY(document_id, node_id)
                    );
                    CREATE INDEX IF NOT EXISTS mindmap_nodes_document_idx ON document_mindmap_nodes(document_id, ordinal);
                    CREATE TABLE IF NOT EXISTS knowledge_collections (
                        id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, created_at REAL NOT NULL,
                        retrieval_config_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE TABLE IF NOT EXISTS document_collections (
                        document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                        collection_id TEXT NOT NULL REFERENCES knowledge_collections(id) ON DELETE RESTRICT
                    );
                    CREATE INDEX IF NOT EXISTS document_collections_collection_idx ON document_collections(collection_id);
                    """
                )
                connection.execute(
                    """INSERT INTO knowledge_collections (id, name, description, created_at)
                       SELECT ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM knowledge_collections)""",
                    ("collection-general", "通用资料", "未分类的本地资料", time.time()),
                )
                collection_columns = {row["name"] for row in connection.execute("PRAGMA table_info(knowledge_collections)")}
                if "retrieval_config_json" not in collection_columns:
                    connection.execute("ALTER TABLE knowledge_collections ADD COLUMN retrieval_config_json TEXT NOT NULL DEFAULT '{}'")
                edge_columns = {row["name"] for row in connection.execute("PRAGMA table_info(graph_edges)")}
                if "evidence_chunk_id" not in edge_columns:
                    connection.executescript("""
                        ALTER TABLE graph_edges RENAME TO graph_edges_legacy;
                        CREATE TABLE graph_edges (
                            source_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                            target_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                            relation TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                            evidence_chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
                            confidence REAL NOT NULL DEFAULT 1.0,
                            UNIQUE(source_id, target_id, relation, document_id, evidence_chunk_id)
                        );
                        INSERT INTO graph_edges (source_id, target_id, relation, document_id, confidence)
                        SELECT source_id, target_id, relation, document_id, 1.0 FROM graph_edges_legacy;
                        DROP TABLE graph_edges_legacy;
                        CREATE INDEX IF NOT EXISTS graph_edges_document_idx ON graph_edges(document_id);
                    """)
                elif "confidence" not in edge_columns:
                    connection.execute("ALTER TABLE graph_edges ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0")
                connection.execute(
                    "INSERT OR IGNORE INTO document_collections (document_id, collection_id) SELECT id, ? FROM documents",
                    ("collection-general",),
                )
                chunk_columns = {row["name"] for row in connection.execute("PRAGMA table_info(chunks)")}
                if "parent_id" not in chunk_columns:
                    connection.execute(
                        "ALTER TABLE chunks ADD COLUMN parent_id TEXT REFERENCES chunks(id) ON DELETE CASCADE"
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS knowledge_meta (
                        key TEXT PRIMARY KEY, value TEXT NOT NULL
                    )"""
                )
                connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise SqliteKnowledgeRepositoryError("unable to initialise knowledge database") from exc

    def save_document_with_chunks(
        self, document: KnowledgeDocument, chunks: list[ChunkDraft | ChunkGroup | KnowledgeChunk], *, collection_id: str = "collection-general"
    ) -> None:
        if not isinstance(document, KnowledgeDocument):
            raise ValueError("document must be a KnowledgeDocument")
        persisted_chunks = self._normalise_chunks(document.id, chunks)
        self._validate_collection_id(collection_id)
        try:
            with self._write_transaction() as connection:
                self._collection_exists(connection, collection_id)
                self._insert_document_with_chunks(connection, document, persisted_chunks, collection_id)
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to save knowledge document") from exc

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge document") from exc
        return self._document_from_row(row) if row is not None else None

    def list_documents(self, collection_id: str | None = None) -> list[KnowledgeDocument]:
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT d.* FROM documents d JOIN document_collections dc ON dc.document_id=d.id "
                    + ("WHERE dc.collection_id=? " if collection_id else "") + "ORDER BY d.created_at, d.id",
                    (collection_id,) if collection_id else (),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to list knowledge documents") from exc
        return [self._document_from_row(row) for row in rows]

    def keyword_search(self, query: str, limit: int, collection_id: str | None = None) -> list[KeywordSearchHit]:
        self._validate_text(query, "query")
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """SELECT f.chunk_id, c.document_id, d.title, c.content, c.location,
                              -bm25(chunks_fts) AS score
                       FROM chunks_fts AS f
                       JOIN chunks AS c ON c.id = f.chunk_id
                       JOIN documents AS d ON d.id = c.document_id
                       JOIN document_collections AS dc ON dc.document_id = d.id
                       WHERE chunks_fts MATCH ?
                         AND NOT EXISTS (SELECT 1 FROM chunks AS child WHERE child.parent_id = c.id)
                       """ + ("AND dc.collection_id = ? " if collection_id else "") + """
                       ORDER BY score DESC, c.ordinal ASC
                       LIMIT ?""",
                    (self._fts_query(query), *( (collection_id,) if collection_id else () ), limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to search knowledge documents") from exc
        return [KeywordSearchHit(**dict(row)) for row in rows]

    def delete_document(self, document_id: str) -> KnowledgeDocument | None:
        self._validate_document_id(document_id)
        try:
            with self._write_transaction() as connection:
                row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
                if row is None:
                    return None
                connection.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)",
                    (document_id,),
                )
                self._delete_vec_rows(connection, document_id)
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to delete knowledge document") from exc
        return self._document_from_row(row)

    def move_document(self, document_id: str, collection_id: str) -> KnowledgeDocument:
        self._validate_document_id(document_id)
        self._validate_collection_id(collection_id)
        try:
            with self._write_transaction() as connection:
                self._collection_exists(connection, collection_id)
                if connection.execute("UPDATE document_collections SET collection_id=? WHERE document_id=?", (collection_id, document_id)).rowcount == 0:
                    raise ValueError("知识资料不存在")
                row = connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to move knowledge document") from exc
        return self._document_from_row(row)

    def update_document_status(self, document_id: str, status: str, error_message: str | None = None) -> KnowledgeDocument:
        self._validate_document_id(document_id)
        if status not in {"queued", "indexing", "ready", "failed"}:
            raise ValueError("invalid knowledge document status")
        try:
            with self._write_transaction() as connection:
                connection.execute("UPDATE documents SET status=?, error_message=?, updated_at=? WHERE id=?", (status, error_message, time.time(), document_id))
                row = connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
                if row is None: raise ValueError("unknown knowledge document")
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to update knowledge document status") from exc
        return self._document_from_row(row)

    def replace_document_chunks(self, document_id: str, chunks: list[ChunkDraft | ChunkGroup | KnowledgeChunk]) -> list[KnowledgeChunk]:
        self._validate_document_id(document_id)
        persisted = self._normalise_chunks(document_id, chunks)
        try:
            with self._write_transaction() as connection:
                document = connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
                if document is None: raise ValueError("unknown knowledge document")
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                self._delete_vec_rows(connection, document_id)
                connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                for chunk in persisted:
                    connection.execute("INSERT INTO chunks (id, document_id, ordinal, content, location, content_hash, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (chunk.id, chunk.document_id, chunk.ordinal, chunk.content, chunk.location, chunk.content_hash, chunk.parent_id))
                    connection.execute("INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)", (chunk.id, self._fts_text(document["title"]), self._fts_text(chunk.content)))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to replace knowledge chunks") from exc
        return persisted

    def update_document_text(self, document_id: str, title: str, chunks: list[ChunkDraft | ChunkGroup | KnowledgeChunk], *, size_bytes: int | None = None) -> KnowledgeDocument:
        self._validate_document_id(document_id)
        if not isinstance(title, str) or not (clean_title := title.strip()) or len(clean_title) > 200:
            raise ValueError("资料标题应为 1 到 200 个字符")
        persisted = self._normalise_chunks(document_id, chunks)
        if size_bytes is not None and (isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0):
            raise ValueError("invalid knowledge document size")
        try:
            with self._write_transaction() as connection:
                if connection.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone() is None:
                    raise ValueError("unknown knowledge document")
                now = time.time()
                if size_bytes is None:
                    connection.execute("UPDATE documents SET title=?, status='queued', error_message=NULL, updated_at=? WHERE id=?", (clean_title, now, document_id))
                else:
                    connection.execute("UPDATE documents SET title=?, size_bytes=?, status='queued', error_message=NULL, updated_at=? WHERE id=?", (clean_title, size_bytes, now, document_id))
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                self._delete_vec_rows(connection, document_id)
                connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                for chunk in persisted:
                    connection.execute("INSERT INTO chunks (id, document_id, ordinal, content, location, content_hash, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (chunk.id, chunk.document_id, chunk.ordinal, chunk.content, chunk.location, chunk.content_hash, chunk.parent_id))
                    connection.execute("INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)", (chunk.id, self._fts_text(clean_title), self._fts_text(chunk.content)))
                row = connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to update knowledge document") from exc
        return self._document_from_row(row)

    def update_chunk(self, chunk_id: str, content: str, location: str | None = None) -> KnowledgeChunk:
        self._validate_chunk_id(chunk_id)
        if not isinstance(content, str) or not (clean_content := content.strip()) or len(clean_content) > 50000:
            raise ValueError("切片内容应为 1 到 50000 个字符")
        clean_location = location.strip() if isinstance(location, str) and location.strip() else None
        try:
            with self._write_transaction() as connection:
                row = connection.execute(
                    "SELECT c.*, d.title FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id=?", (chunk_id,)
                ).fetchone()
                if row is None:
                    raise ValueError("unknown knowledge chunk")
                connection.execute(
                    "INSERT INTO chunk_revisions (id, chunk_id, content, location, created_at) VALUES (?, ?, ?, ?, ?)",
                    (f"revision-{uuid4().hex}", chunk_id, row["content"], row["location"], time.time()),
                )
                content_hash = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()
                connection.execute("UPDATE chunks SET content=?, location=?, content_hash=? WHERE id=?", (clean_content, clean_location, content_hash, chunk_id))
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
                connection.execute("INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)", (chunk_id, self._fts_text(row["title"]), self._fts_text(clean_content)))
                connection.execute("DELETE FROM chunk_embeddings WHERE chunk_id=?", (chunk_id,))
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_vec'").fetchone():
                    connection.execute("DELETE FROM chunks_vec WHERE chunk_id=?", (chunk_id,))
                connection.execute("UPDATE documents SET updated_at=? WHERE id=?", (time.time(), row["document_id"]))
                updated = connection.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to update knowledge chunk") from exc
        return KnowledgeChunk(**dict(updated))

    def chunk_revisions(self, chunk_id: str, limit: int = 20) -> list[dict[str, object]]:
        self._validate_chunk_id(chunk_id)
        self._validate_limit(limit)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT id, chunk_id, content, location, created_at FROM chunk_revisions WHERE chunk_id=? ORDER BY created_at DESC LIMIT ?",
                    (chunk_id, min(limit, 100)),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge chunk revisions") from exc
        return [dict(row) for row in rows]

    def restore_chunk_revision(self, chunk_id: str, revision_id: str) -> KnowledgeChunk:
        self._validate_chunk_id(chunk_id)
        if not isinstance(revision_id, str) or not re.fullmatch(r"revision-[0-9a-f]{32}", revision_id):
            raise ValueError("invalid knowledge chunk revision id")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT content, location FROM chunk_revisions WHERE id=? AND chunk_id=?", (revision_id, chunk_id)
                ).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge chunk revision") from exc
        if row is None:
            raise ValueError("unknown knowledge chunk revision")
        return self.update_chunk(chunk_id, row["content"], row["location"])

    def save_embeddings(self, document_id: str, model: str, mappings: EmbeddingMappings) -> None:
        self._validate_document_id(document_id)
        self._validate_text(model, "embedding model")
        items = list(mappings.items()) if isinstance(mappings, Mapping) else list(mappings)
        normalised = [(self._validate_embedding(chunk_id, vector)) for chunk_id, vector in items]
        try:
            with self._write_transaction() as connection:
                if connection.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
                    raise ValueError("unknown knowledge document")
                vec_ready = self._ensure_vec_table(connection, normalised[0][2]) if normalised else True
                for chunk_id, vector, dimensions in normalised:
                    row = connection.execute(
                        "SELECT content_hash FROM chunks WHERE id = ? AND document_id = ?", (chunk_id, document_id)
                    ).fetchone()
                    if row is None:
                        raise ValueError("embedding chunk does not belong to document")
                    connection.execute(
                        """INSERT INTO chunk_embeddings (chunk_id, model, dimensions, vector_json, content_hash, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(chunk_id) DO UPDATE SET model = excluded.model,
                               dimensions = excluded.dimensions, vector_json = excluded.vector_json,
                               content_hash = excluded.content_hash, created_at = excluded.created_at""",
                        (chunk_id, model, dimensions, json.dumps(vector), row["content_hash"], time.time()),
                    )
                    if vec_ready:
                        connection.execute("DELETE FROM chunks_vec WHERE chunk_id = ?", (chunk_id,))
                        connection.execute(
                            "INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                            (chunk_id, json.dumps(vector)),
                        )
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to save knowledge embeddings") from exc

    def embedding_count(self, document_id: str) -> int:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT COUNT(*) AS count FROM chunk_embeddings AS e
                       JOIN chunks AS c ON c.id = e.chunk_id WHERE c.document_id = ?""",
                    (document_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to count knowledge embeddings") from exc
        return int(row["count"])

    def embedding_candidates(self, limit: int | None = None, collection_id: str | None = None) -> list[EmbeddingSearchCandidate]:
        if limit is not None:
            self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                sql = (
                    """SELECT e.chunk_id, c.document_id, d.title, c.content, c.location, e.vector_json
                       FROM chunk_embeddings AS e JOIN chunks AS c ON c.id = e.chunk_id
                       JOIN documents AS d ON d.id = c.document_id
                       JOIN document_collections AS dc ON dc.document_id = d.id
                       WHERE d.status = 'ready'
                         AND NOT EXISTS (SELECT 1 FROM chunks AS child WHERE child.parent_id = c.id) """
                    + ("AND dc.collection_id = ? " if collection_id else "")
                    + "ORDER BY d.created_at, c.ordinal"
                    + (" LIMIT ?" if limit is not None else "")
                )
                params = (*((collection_id,) if collection_id else ()), *((limit,) if limit is not None else ()))
                rows = connection.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge embeddings") from exc
        return [EmbeddingSearchCandidate(
            chunk_id=row["chunk_id"], document_id=row["document_id"], title=row["title"],
            content=row["content"], location=row["location"], vector=json.loads(row["vector_json"]),
        ) for row in rows]

    @staticmethod
    def _delete_vec_rows(connection: sqlite3.Connection, document_id: str) -> None:
        """The vec0 virtual table has no foreign keys; drop stale ANN rows by hand."""
        if _sqlite_vec is None:
            return
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
        ).fetchone()
        if exists is None:
            return
        connection.execute(
            "DELETE FROM chunks_vec WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)",
            (document_id,),
        )

    def _ensure_vec_table(self, connection: sqlite3.Connection, dimensions: int) -> bool:
        """Create (or rebuild) the sqlite-vec ANN table; returns False when unavailable."""
        if _sqlite_vec is None:
            return False
        row = connection.execute("SELECT value FROM knowledge_meta WHERE key = 'vec_dimensions'").fetchone()
        if row is not None:
            try:
                stored = int(row["value"])
            except (TypeError, ValueError):
                stored = None
            if stored == dimensions:
                return True
            if stored is not None:
                connection.execute("DROP TABLE IF EXISTS chunks_vec")
        connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
            f"chunk_id TEXT PRIMARY KEY, embedding float[{dimensions}] distance_metric=cosine)"
        )
        connection.execute(
            "INSERT INTO knowledge_meta (key, value) VALUES ('vec_dimensions', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(dimensions),),
        )
        return True

    def backfill_vector_index(self) -> int:
        """(Re)build the ANN index from stored JSON vectors; returns indexed rows, 0 when unavailable."""
        if _sqlite_vec is None:
            return 0
        try:
            with self._write_transaction() as connection:
                row = connection.execute(
                    "SELECT dimensions FROM chunk_embeddings GROUP BY dimensions ORDER BY COUNT(*) DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    return 0
                dimensions = int(row["dimensions"])
                if not self._ensure_vec_table(connection, dimensions):
                    return 0
                connection.execute("DELETE FROM chunks_vec")
                for item in connection.execute(
                    "SELECT chunk_id, vector_json FROM chunk_embeddings WHERE dimensions = ?", (dimensions,)
                ).fetchall():
                    connection.execute("INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)", (item["chunk_id"], item["vector_json"]))
                count = connection.execute("SELECT COUNT(*) AS count FROM chunks_vec").fetchone()["count"]
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to build vector index") from exc
        return int(count)

    def embedding_search(self, query_vector: Sequence[float], limit: int, collection_id: str | None = None) -> list[EmbeddingSearchHit]:
        """Search the ANN index, with an exact cosine fallback when unavailable."""
        self._validate_limit(limit)
        if collection_id is not None:
            self._validate_collection_id(collection_id)
        values = [float(value) for value in query_vector]
        if not values or not all(math.isfinite(value) for value in values):
            raise ValueError("query vector must be finite")
        if _sqlite_vec is None:
            return self._cosine_embedding_search(values, limit, collection_id)
        fetch_limit = limit * 4 if collection_id is not None else limit
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
                ).fetchone()
                if exists is None:
                    return self._cosine_embedding_search(values, limit, collection_id)
                rows = connection.execute(
                    """SELECT ann.chunk_id, 1.0 - ann.distance AS similarity, c.document_id, d.title, c.content, c.location
                       FROM (SELECT chunk_id, distance FROM chunks_vec WHERE embedding MATCH ? AND k = ?) AS ann
                       JOIN chunks AS c ON c.id = ann.chunk_id
                       JOIN documents AS d ON d.id = c.document_id AND d.status = 'ready'
                       JOIN document_collections AS dc ON dc.document_id = d.id
                       WHERE NOT EXISTS (SELECT 1 FROM chunks AS child WHERE child.parent_id = c.id)
                       """ + ("AND dc.collection_id = ? " if collection_id else "") + "ORDER BY ann.distance",
                    (json.dumps(values), fetch_limit, *((collection_id,) if collection_id else ())),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to run vector search") from exc
        return [EmbeddingSearchHit(
            chunk_id=row["chunk_id"], document_id=row["document_id"], title=row["title"],
            content=row["content"], location=row["location"], similarity=float(row["similarity"]),
        ) for row in rows[:limit]]

    def _cosine_embedding_search(
        self, query_vector: Sequence[float], limit: int, collection_id: str | None
    ) -> list[EmbeddingSearchHit]:
        ranked_candidates = sorted(
            (
                (self._cosine_similarity(query_vector, candidate.vector), candidate)
                for candidate in self.embedding_candidates(collection_id=collection_id)
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        return [
            EmbeddingSearchHit(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                title=candidate.title,
                content=candidate.content,
                location=candidate.location,
                similarity=similarity,
            )
            for similarity, candidate in ranked_candidates[:limit]
        ]

    @staticmethod
    def _cosine_similarity(left_vector: Sequence[float], right_vector: Sequence[float]) -> float:
        if len(left_vector) != len(right_vector):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left_vector))
        right_norm = math.sqrt(sum(value * value for value in right_vector))
        if not left_norm or not right_norm:
            return 0.0
        return sum(left_value * right_value for left_value, right_value in zip(left_vector, right_vector)) / (left_norm * right_norm)

    def parent_context_for(self, chunk_ids: Sequence[str]) -> dict[str, KnowledgeChunk]:
        """Map each chunk id to its parent chunk, or to itself when it has no parent."""
        ids = [chunk_id for chunk_id in dict.fromkeys(chunk_ids or []) if isinstance(chunk_id, str)]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(f"SELECT * FROM chunks WHERE id IN ({placeholders})", ids).fetchall()
                parent_ids = sorted({row["parent_id"] for row in rows if row["parent_id"]})
                parents: dict[str, sqlite3.Row] = {}
                if parent_ids:
                    parent_placeholders = ",".join("?" for _ in parent_ids)
                    parents = {
                        row["id"]: row
                        for row in connection.execute(f"SELECT * FROM chunks WHERE id IN ({parent_placeholders})", parent_ids).fetchall()
                    }
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read parent chunks") from exc
        result: dict[str, KnowledgeChunk] = {}
        for row in rows:
            context_row = parents.get(row["parent_id"]) or row
            result[row["id"]] = KnowledgeChunk(**dict(context_row))
        return result

    def chunks_for_document(self, document_id: str) -> list[KnowledgeChunk]:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal", (document_id,)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge chunks") from exc
        return [KnowledgeChunk(**dict(row)) for row in rows]

    def replace_document_graph(self, document_id: str, entities: Iterable[tuple[str, str]], relations: Iterable[tuple[str, str, str, str | None, float]]) -> None:
        self._validate_document_id(document_id)
        try:
            with self._write_transaction() as connection:
                connection.execute("DELETE FROM graph_edges WHERE document_id = ?", (document_id,))
                ids: dict[str, str] = {}
                for label, kind in entities:
                    label, kind = label.strip()[:120], kind.strip()[:40]
                    if not label or not kind: continue
                    node_id = f"node-{hashlib.sha256(label.casefold().encode('utf-8')).hexdigest()[:24]}"
                    connection.execute("INSERT OR IGNORE INTO graph_nodes (id, label, kind) VALUES (?, ?, ?)", (node_id, label, kind))
                    row = connection.execute("SELECT id FROM graph_nodes WHERE id = ? OR label = ? LIMIT 1", (node_id, label)).fetchone()
                    ids[label] = row["id"]
                for source, target, relation, evidence_chunk_id, confidence in relations:
                    if source in ids and target in ids and ids[source] != ids[target]:
                        if evidence_chunk_id is not None:
                            row = connection.execute("SELECT 1 FROM chunks WHERE id=? AND document_id=?", (evidence_chunk_id, document_id)).fetchone()
                            if row is None: evidence_chunk_id = None
                        connection.execute("""INSERT OR IGNORE INTO graph_edges
                            (source_id, target_id, relation, document_id, evidence_chunk_id, confidence)
                            VALUES (?, ?, ?, ?, ?, ?)""", (ids[source], ids[target], relation[:80] or "关联", document_id, evidence_chunk_id, max(0.0, min(float(confidence), 1.0))))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to save knowledge graph") from exc

    def replace_document_mindmap(self, document_id: str, nodes: Iterable[MindMapNode]) -> None:
        self._validate_document_id(document_id)
        values = list(nodes)
        if not values or values[0].parent_id is not None:
            raise ValueError("mind map must have one root node")
        known = {node.id for node in values}
        if any(node.parent_id is not None and node.parent_id not in known for node in values):
            raise ValueError("mind map parent does not exist")
        try:
            with self._write_transaction() as connection:
                if connection.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone() is None:
                    raise ValueError("knowledge document does not exist")
                connection.execute("DELETE FROM document_mindmap_nodes WHERE document_id=?", (document_id,))
                connection.executemany(
                    """INSERT INTO document_mindmap_nodes
                       (document_id, node_id, parent_id, label, summary, kind, ordinal, evidence_chunk_ids_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (document_id, node.id, node.parent_id, node.label, node.summary, node.kind, node.ordinal,
                         json.dumps(list(node.evidence_chunk_ids), ensure_ascii=False))
                        for node in values
                    ],
                )
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to save document mind map") from exc

    def document_mindmap(self, document_id: str) -> list[MindMapNode]:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """SELECT node_id, parent_id, label, summary, kind, ordinal, evidence_chunk_ids_json
                       FROM document_mindmap_nodes WHERE document_id=?
                       ORDER BY CASE kind WHEN 'root' THEN 0 WHEN 'branch' THEN 1 ELSE 2 END, ordinal, node_id""",
                    (document_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read document mind map") from exc
        return [MindMapNode(row["node_id"], row["parent_id"], row["label"], row["summary"], row["kind"], row["ordinal"], tuple(json.loads(row["evidence_chunk_ids_json"]))) for row in rows]

    def graph(self, topic: str | None = None, limit: int = 200, collection_id: str | None = None) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                clause, args = "", []
                if topic and topic.strip():
                    clause, args = "AND lower(n.label) = lower(?)", [topic.strip()]
                nodes = connection.execute(f"""SELECT n.id, n.label, n.kind, COUNT(DISTINCT e.document_id) AS document_count
                    FROM graph_nodes n JOIN graph_edges e ON n.id=e.source_id OR n.id=e.target_id
                    JOIN document_collections dc ON dc.document_id=e.document_id
                    WHERE 1=1 {('AND dc.collection_id = ?' if collection_id else '')} {clause}
                    GROUP BY n.id ORDER BY document_count DESC, n.label LIMIT ?""", (*( (collection_id,) if collection_id else () ), *args, limit)).fetchall()
                node_ids = {row['id'] for row in nodes}
                if not node_ids: return [], []
                marks = ','.join('?' for _ in node_ids)
                edges = connection.execute(f"""SELECT e.source_id AS source, e.target_id AS target, e.relation, e.document_id, e.evidence_chunk_id, e.confidence, substr(c.content, 1, 600) AS evidence
                    FROM graph_edges e JOIN document_collections dc ON dc.document_id=e.document_id LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                    WHERE (e.source_id IN ({marks}) OR e.target_id IN ({marks})) {('AND dc.collection_id = ?' if collection_id else '')} LIMIT ?""",
                    (*node_ids, *node_ids, *( (collection_id,) if collection_id else () ), limit * 3)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge graph") from exc
        return [KnowledgeGraphNode(**dict(row)) for row in nodes], [KnowledgeGraphEdge(**dict(row)) for row in edges]

    def graph_context(self, document_ids: Sequence[str], collection_id: str | None = None, limit: int = 12) -> list[dict[str, str | float | None]]:
        """Return grounded relations for retrieved documents, including the source chunk text."""
        if not document_ids: return []
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        for document_id in document_ids: self._validate_document_id(document_id)
        marks = ",".join("?" for _ in document_ids)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(f"""SELECT source.label AS source, target.label AS target, e.relation,
                    e.confidence, e.document_id, d.title, e.evidence_chunk_id, c.content AS evidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id
                    JOIN graph_nodes target ON target.id=e.target_id
                    JOIN documents d ON d.id=e.document_id
                    JOIN document_collections dc ON dc.document_id=e.document_id
                    LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                    WHERE e.document_id IN ({marks}) {('AND dc.collection_id=?' if collection_id else '')}
                    ORDER BY e.confidence DESC LIMIT ?""", (*document_ids, *((collection_id,) if collection_id else ()), limit)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read graph context") from exc
        return [dict(row) for row in rows]

    def global_graph_context(self, query: str, collection_id: str | None = None, limit: int = 16) -> list[dict[str, str | float | None]]:
        """Retrieve graph facts relevant to a broad question before falling back to high-confidence facts."""
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        terms = [item for item in re.findall(r"[A-Za-z][A-Za-z0-9+.#_-]{1,40}|[\u4e00-\u9fff]{2,12}", query) if len(item) >= 2][:6]
        try:
            with closing(self._connect()) as connection:
                clause = " OR ".join("lower(source.label) LIKE ? OR lower(target.label) LIKE ? OR lower(e.relation) LIKE ?" for _ in terms)
                params: list[object] = []
                for term in terms: params.extend([f"%{term.lower()}%"] * 3)
                where = f"AND ({clause})" if clause else ""
                rows = connection.execute(f"""SELECT source.label AS source, target.label AS target, e.relation, e.confidence, e.document_id, d.title, e.evidence_chunk_id, c.content AS evidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id
                    JOIN documents d ON d.id=e.document_id
                    JOIN document_collections dc ON dc.document_id=e.document_id LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                    WHERE 1=1 {('AND dc.collection_id=?' if collection_id else '')} {where}
                    ORDER BY e.confidence DESC LIMIT ?""", (*((collection_id,) if collection_id else ()), *params, limit)).fetchall()
                if not rows and terms:
                    rows = connection.execute("""SELECT source.label AS source, target.label AS target, e.relation, e.confidence, e.document_id, d.title, e.evidence_chunk_id, c.content AS evidence
                        FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id
                        JOIN documents d ON d.id=e.document_id
                        JOIN document_collections dc ON dc.document_id=e.document_id LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                        WHERE 1=1 """ + ("AND dc.collection_id=? " if collection_id else "") + "ORDER BY e.confidence DESC LIMIT ?", (*((collection_id,) if collection_id else ()), limit)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to search global graph context") from exc
        return [dict(row) for row in rows]

    def graph_search(self, query: str, limit: int = 20, collection_id: str | None = None) -> list[KeywordSearchHit]:
        """Return source chunks reached through matching graph entities and relations."""
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        terms = [item.casefold() for item in re.findall(r"[A-Za-z][A-Za-z0-9+.#_-]{1,40}|[\u4e00-\u9fff]{2,12}", query)][:6]
        if not terms:
            return []
        predicates = " OR ".join("lower(source.label) LIKE ? OR lower(target.label) LIKE ? OR lower(e.relation) LIKE ?" for _ in terms)
        parameters: list[object] = []
        for term in terms:
            parameters.extend([f"%{term}%"] * 3)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(f"""SELECT DISTINCT c.id AS chunk_id, c.document_id, d.title, c.content, c.location, e.confidence AS score
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id
                    JOIN graph_nodes target ON target.id=e.target_id
                    JOIN chunks c ON c.id=e.evidence_chunk_id JOIN documents d ON d.id=c.document_id
                    JOIN document_collections dc ON dc.document_id=e.document_id
                    WHERE ({predicates}) {('AND dc.collection_id=?' if collection_id else '')}
                    ORDER BY e.confidence DESC LIMIT ?""", (*parameters, *((collection_id,) if collection_id else ()), limit)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to search graph evidence") from exc
        return [KeywordSearchHit(**dict(row)) for row in rows]

    def graph_entity_evidence(self, node_id: str, collection_id: str | None = None, limit: int = 6) -> list[dict[str, str | float | None]]:
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("""SELECT source.label AS source, target.label AS target, e.relation, e.confidence, c.content AS evidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id
                    JOIN document_collections dc ON dc.document_id=e.document_id LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                    WHERE (e.source_id=? OR e.target_id=?) """ + ("AND dc.collection_id=? " if collection_id else "") + "ORDER BY e.confidence DESC LIMIT ?", (node_id, node_id, *((collection_id,) if collection_id else ()), limit)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read graph entity evidence") from exc
        return [dict(row) for row in rows]

    def graph_node_label(self, node_id: str) -> str | None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT label FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read graph node") from exc
        return str(row["label"]) if row else None

    def graph_relation_evidence(self, source_id: str, target_id: str, relation: str, document_id: str | None = None, collection_id: str | None = None, limit: int = 6) -> list[dict[str, str | float | None]]:
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        where = "e.source_id=? AND e.target_id=? AND e.relation=?"
        values: list[object] = [source_id, target_id, relation]
        if document_id:
            where += " AND e.document_id=?"; values.append(document_id)
        if collection_id:
            where += " AND dc.collection_id=?"; values.append(collection_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(f"""SELECT source.label AS source, target.label AS target, e.relation, e.confidence, c.content AS evidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id
                    JOIN document_collections dc ON dc.document_id=e.document_id LEFT JOIN chunks c ON c.id=e.evidence_chunk_id
                    WHERE {where} ORDER BY e.confidence DESC LIMIT ?""", (*values, limit)).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read graph relation evidence") from exc
        return [dict(row) for row in rows]

    def graph_audit(self, collection_id: str | None = None, limit: int = 30) -> dict[str, object]:
        """Identify graph records that should be reviewed; this method never changes data."""
        self._validate_limit(limit)
        if collection_id is not None: self._validate_collection_id(collection_id)
        scope = "JOIN document_collections dc ON dc.document_id=e.document_id "
        filter_sql = "WHERE dc.collection_id=?" if collection_id else ""
        args = (collection_id,) if collection_id else ()
        try:
            with closing(self._connect()) as connection:
                low = connection.execute(f"""SELECT source.label AS source, target.label AS target, e.relation, e.document_id, e.confidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id {scope}
                    {filter_sql} {'AND' if filter_sql else 'WHERE'} e.confidence < .5 ORDER BY e.confidence LIMIT ?""", (*args, limit)).fetchall()
                missing = connection.execute(f"""SELECT source.label AS source, target.label AS target, e.relation, e.document_id, e.confidence
                    FROM graph_edges e JOIN graph_nodes source ON source.id=e.source_id JOIN graph_nodes target ON target.id=e.target_id {scope}
                    {filter_sql} {'AND' if filter_sql else 'WHERE'} (e.evidence_chunk_id IS NULL OR NOT EXISTS(SELECT 1 FROM chunks c WHERE c.id=e.evidence_chunk_id)) ORDER BY e.confidence LIMIT ?""", (*args, limit)).fetchall()
                labels = connection.execute(f"""SELECT DISTINCT n.label FROM graph_nodes n JOIN graph_edges e ON n.id=e.source_id OR n.id=e.target_id {scope} {filter_sql}""", args).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to audit knowledge graph") from exc
        groups: dict[str, list[str]] = {}
        for row in labels:
            label = str(row["label"]); normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", label.casefold())
            if normalized: groups.setdefault(normalized, []).append(label)
        duplicates = [values for values in groups.values() if len(set(values)) > 1][:limit]
        return {"low_confidence": [dict(row) for row in low], "missing_evidence": [dict(row) for row in missing], "similar_labels": duplicates,
                "counts": {"low_confidence": len(low), "missing_evidence": len(missing), "similar_labels": len(duplicates)}}

    def update_graph_edge_relation(self, source_id: str, target_id: str, relation: str, new_relation: str, document_id: str | None = None) -> int:
        relation, new_relation = relation.strip()[:80], new_relation.strip()[:80]
        if not relation or not new_relation:
            raise ValueError("关系名称不能为空")
        where, values = "source_id=? AND target_id=? AND relation=?", [source_id, target_id, relation]
        if document_id:
            where += " AND document_id=?"; values.append(document_id)
        try:
            with self._write_transaction() as connection:
                rows = connection.execute(f"SELECT source_id, target_id, relation, document_id, evidence_chunk_id, confidence FROM graph_edges WHERE {where}", values).fetchall()
                for row in rows:
                    connection.execute("INSERT OR IGNORE INTO graph_edges (source_id, target_id, relation, document_id, evidence_chunk_id, confidence) VALUES (?, ?, ?, ?, ?, ?)", (row["source_id"], row["target_id"], new_relation, row["document_id"], row["evidence_chunk_id"], row["confidence"]))
                if rows:
                    connection.execute(f"DELETE FROM graph_edges WHERE {where}", values)
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to update graph relation") from exc
        return len(rows)

    def delete_graph_edge(self, source_id: str, target_id: str, relation: str, document_id: str | None = None) -> int:
        where, values = "source_id=? AND target_id=? AND relation=?", [source_id, target_id, relation]
        if document_id:
            where += " AND document_id=?"; values.append(document_id)
        try:
            with self._write_transaction() as connection:
                deleted = connection.execute(f"DELETE FROM graph_edges WHERE {where}", values).rowcount
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to delete graph relation") from exc
        return deleted

    def rename_graph_entity(self, node_id: str, new_label: str, collection_id: str) -> int:
        """Replace one entity only in the selected collection, preserving other collections."""
        self._validate_collection_id(collection_id)
        label = new_label.strip()[:120]
        if not label:
            raise ValueError("实体名称不能为空")
        try:
            with self._write_transaction() as connection:
                self._collection_exists(connection, collection_id)
                old = connection.execute("SELECT id, kind FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
                if old is None: raise ValueError("图谱实体不存在")
                existing = connection.execute("SELECT id FROM graph_nodes WHERE label=?", (label,)).fetchone()
                target_id = existing["id"] if existing else f"node-{hashlib.sha256(label.casefold().encode('utf-8')).hexdigest()[:24]}"
                if existing is None: connection.execute("INSERT INTO graph_nodes (id, label, kind) VALUES (?, ?, ?)", (target_id, label, old["kind"]))
                rows = connection.execute("""SELECT e.source_id, e.target_id, e.relation, e.document_id, e.evidence_chunk_id, e.confidence
                    FROM graph_edges e JOIN document_collections dc ON dc.document_id=e.document_id
                    WHERE (e.source_id=? OR e.target_id=?) AND dc.collection_id=?""", (node_id, node_id, collection_id)).fetchall()
                for row in rows:
                    source_id = target_id if row["source_id"] == node_id else row["source_id"]
                    target = target_id if row["target_id"] == node_id else row["target_id"]
                    if source_id != target:
                        connection.execute("INSERT OR IGNORE INTO graph_edges (source_id, target_id, relation, document_id, evidence_chunk_id, confidence) VALUES (?, ?, ?, ?, ?, ?)", (source_id, target, row["relation"], row["document_id"], row["evidence_chunk_id"], row["confidence"]))
                    connection.execute("DELETE FROM graph_edges WHERE source_id=? AND target_id=? AND relation=? AND document_id=? AND evidence_chunk_id IS ?", (row["source_id"], row["target_id"], row["relation"], row["document_id"], row["evidence_chunk_id"]))
                connection.execute("DELETE FROM graph_nodes WHERE id=? AND id NOT IN (SELECT source_id FROM graph_edges UNION SELECT target_id FROM graph_edges)", (node_id,))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to rename graph entity") from exc
        return len(rows)

    def delete_graph_entity(self, node_id: str, collection_id: str) -> int:
        self._validate_collection_id(collection_id)
        try:
            with self._write_transaction() as connection:
                rows = connection.execute("""SELECT e.source_id, e.target_id, e.relation, e.document_id, e.evidence_chunk_id
                    FROM graph_edges e JOIN document_collections dc ON dc.document_id=e.document_id
                    WHERE (e.source_id=? OR e.target_id=?) AND dc.collection_id=?""", (node_id, node_id, collection_id)).fetchall()
                for row in rows:
                    connection.execute("DELETE FROM graph_edges WHERE source_id=? AND target_id=? AND relation=? AND document_id=? AND evidence_chunk_id IS ?", (row["source_id"], row["target_id"], row["relation"], row["document_id"], row["evidence_chunk_id"]))
                connection.execute("DELETE FROM graph_nodes WHERE id=? AND id NOT IN (SELECT source_id FROM graph_edges UNION SELECT target_id FROM graph_edges)", (node_id,))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to delete graph entity") from exc
        return len(rows)

    def prune_orphan_graph_nodes(self) -> int:
        try:
            with self._write_transaction() as connection:
                return connection.execute("DELETE FROM graph_nodes WHERE id NOT IN (SELECT source_id FROM graph_edges UNION SELECT target_id FROM graph_edges)").rowcount
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to prune graph nodes") from exc

    def graph_entity_labels(self, collection_id: str | None = None) -> list[str]:
        if collection_id is not None: self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("""SELECT DISTINCT n.label FROM graph_nodes n JOIN graph_edges e ON n.id=e.source_id OR n.id=e.target_id
                    JOIN document_collections dc ON dc.document_id=e.document_id WHERE n.kind != 'topic' """ + ("AND dc.collection_id=? " if collection_id else "") + "ORDER BY n.label LIMIT 120", ((collection_id,) if collection_id else ())).fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read graph entities") from exc
        return [str(row["label"]) for row in rows]

    def merge_graph_entities(self, aliases: Mapping[str, str]) -> int:
        pairs = [(source.strip(), target.strip()) for source, target in aliases.items() if source.strip() and target.strip() and source.strip() != target.strip()]
        if not pairs: return 0
        merged = 0
        try:
            with self._write_transaction() as connection:
                for source, target in pairs:
                    old = connection.execute("SELECT id, kind FROM graph_nodes WHERE label=?", (source,)).fetchone()
                    if old is None or old["kind"] == "topic": continue
                    new = connection.execute("SELECT id FROM graph_nodes WHERE label=?", (target,)).fetchone()
                    if new is None:
                        new_id = f"node-{hashlib.sha256(target.casefold().encode('utf-8')).hexdigest()[:24]}"
                        connection.execute("INSERT OR IGNORE INTO graph_nodes (id, label, kind) VALUES (?, ?, ?)", (new_id, target, old["kind"]))
                        new = connection.execute("SELECT id FROM graph_nodes WHERE label=?", (target,)).fetchone()
                    edges = connection.execute("SELECT source_id, target_id, relation, document_id, evidence_chunk_id, confidence FROM graph_edges WHERE source_id=? OR target_id=?", (old["id"], old["id"])).fetchall()
                    for edge in edges:
                        source_id = new["id"] if edge["source_id"] == old["id"] else edge["source_id"]
                        target_id = new["id"] if edge["target_id"] == old["id"] else edge["target_id"]
                        if source_id != target_id:
                            connection.execute("INSERT OR IGNORE INTO graph_edges (source_id, target_id, relation, document_id, evidence_chunk_id, confidence) VALUES (?, ?, ?, ?, ?, ?)", (source_id, target_id, edge["relation"], edge["document_id"], edge["evidence_chunk_id"], edge["confidence"]))
                    connection.execute("DELETE FROM graph_edges WHERE source_id=? OR target_id=?", (old["id"], old["id"]))
                    connection.execute("DELETE FROM graph_nodes WHERE id=?", (old["id"],))
                    merged += 1
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to merge graph entities") from exc
        return merged

    def graph_edge_count(self, document_id: str) -> int:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT COUNT(*) AS count FROM graph_edges WHERE document_id = ?", (document_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to count knowledge graph edges") from exc
        return int(row["count"])

    def graph_node_count(self, document_id: str) -> int:
        self._validate_document_id(document_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT COUNT(DISTINCT node_id) AS count FROM (SELECT source_id AS node_id FROM graph_edges WHERE document_id=? UNION SELECT target_id FROM graph_edges WHERE document_id=?)", (document_id, document_id)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to count knowledge graph nodes") from exc
        return int(row["count"])

    def migrate_legacy(self, legacy: KnowledgeRepository) -> int:
        if not isinstance(legacy, KnowledgeRepository):
            raise ValueError("legacy must be a KnowledgeRepository")
        migrated = 0
        for entry in legacy.list():
            marker = self._legacy_marker(entry)
            document = KnowledgeDocument(
                id=f"doc-{hashlib.sha256(entry.id.encode('utf-8')).hexdigest()[:32]}",
                title=entry.title,
                source_type=entry.source_type,
                media_type="text/plain",
                size_bytes=len(entry.content.encode("utf-8")),
                original_name=self._legacy_original_name(entry),
                status="ready",
                error_message=None,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            chunks = self._normalise_chunks(document.id, [ChunkDraft(entry.content, None)])
            try:
                with self._write_transaction() as connection:
                    exists = connection.execute(
                        "SELECT 1 FROM documents WHERE original_name = ? OR original_name LIKE ?",
                        (marker, f"{marker}\n%"),
                    ).fetchone()
                    if exists is None:
                        self._insert_document_with_chunks(connection, document, chunks, "collection-general")
                        migrated += 1
            except sqlite3.Error as exc:
                raise SqliteKnowledgeRepositoryError("unable to migrate legacy knowledge") from exc
        return migrated

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                if str(journal_mode).lower() != "wal":
                    connection.execute("PRAGMA journal_mode = DELETE")
            except sqlite3.Error:
                connection.execute("PRAGMA journal_mode = DELETE")
            if _sqlite_vec is not None:
                try:
                    connection.enable_load_extension(True)
                    _sqlite_vec.load(connection)
                    connection.enable_load_extension(False)
                except (AttributeError, sqlite3.Error):
                    pass
        except sqlite3.Error:
            connection.close()
            raise
        return connection

    def _write_transaction(self):
        return _ImmediateTransaction(self._connect())

    @staticmethod
    def _document_values(document: KnowledgeDocument) -> tuple[Any, ...]:
        return (
            document.id, document.title, document.source_type, document.media_type, document.size_bytes,
            document.original_name, document.status, document.error_message, document.created_at, document.updated_at,
        )

    def _insert_document_with_chunks(
        self, connection: sqlite3.Connection, document: KnowledgeDocument, chunks: list[KnowledgeChunk], collection_id: str = "collection-general"
    ) -> None:
        """Write related rows on an already-open immediate transaction."""
        connection.execute(
            """INSERT INTO documents (
                id, title, source_type, media_type, size_bytes, original_name, status,
                error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._document_values(document),
        )
        for chunk in chunks:
            connection.execute(
                """INSERT INTO chunks (id, document_id, ordinal, content, location, content_hash, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chunk.id, chunk.document_id, chunk.ordinal, chunk.content, chunk.location, chunk.content_hash, chunk.parent_id),
            )
            connection.execute(
                "INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)",
                (chunk.id, self._fts_text(document.title), self._fts_text(chunk.content)),
            )
        connection.execute("INSERT INTO document_collections (document_id, collection_id) VALUES (?, ?)", (document.id, collection_id))

    def list_collections(self) -> list[KnowledgeCollection]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT * FROM knowledge_collections ORDER BY created_at, name").fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to list knowledge collections") from exc
        return [self._collection_from_row(row) for row in rows]

    def create_collection(self, name: str, description: str | None = None) -> KnowledgeCollection:
        collection = KnowledgeCollection.new(name, description)
        try:
            with self._write_transaction() as connection:
                connection.execute("INSERT INTO knowledge_collections (id, name, description, created_at, retrieval_config_json) VALUES (?, ?, ?, ?, ?)",
                                   (collection.id, collection.name, collection.description, collection.created_at, "{}"))
        except sqlite3.IntegrityError as exc:
            raise ValueError("知识库名称已存在") from exc
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to create knowledge collection") from exc
        return collection

    def delete_collection(self, collection_id: str) -> bool:
        self._validate_collection_id(collection_id)
        try:
            with self._write_transaction() as connection:
                document_rows = connection.execute(
                    "SELECT document_id FROM document_collections WHERE collection_id=?", (collection_id,)
                ).fetchall()
                document_ids = [row["document_id"] for row in document_rows]
                if document_ids:
                    placeholders = ",".join("?" for _ in document_ids)
                    connection.execute(
                        f"DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id IN ({placeholders}))",
                        document_ids,
                    )
                    for document_id in document_ids:
                        self._delete_vec_rows(connection, document_id)
                    connection.execute(f"DELETE FROM documents WHERE id IN ({placeholders})", document_ids)
                deleted = connection.execute("DELETE FROM knowledge_collections WHERE id=?", (collection_id,)).rowcount > 0
                if deleted:
                    connection.execute(
                        "DELETE FROM graph_nodes WHERE id NOT IN (SELECT source_id FROM graph_edges UNION SELECT target_id FROM graph_edges)"
                    )
                return deleted
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to delete knowledge collection") from exc

    def rename_collection(self, collection_id: str, name: str) -> KnowledgeCollection:
        self._validate_collection_id(collection_id)
        if not isinstance(name, str) or not (trimmed := name.strip()) or len(trimmed) > 80:
            raise ValueError("知识库名称应为 1 到 80 个字符")
        try:
            with self._write_transaction() as connection:
                if connection.execute("UPDATE knowledge_collections SET name=? WHERE id=?", (trimmed, collection_id)).rowcount == 0:
                    raise ValueError("知识库不存在")
                row = connection.execute("SELECT * FROM knowledge_collections WHERE id=?", (collection_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("知识库名称已存在") from exc
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to rename knowledge collection") from exc
        return self._collection_from_row(row)

    def collection_retrieval_config(self, collection_id: str) -> dict[str, int | float]:
        self._validate_collection_id(collection_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT retrieval_config_json FROM knowledge_collections WHERE id=?", (collection_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to read knowledge collection retrieval config") from exc
        if row is None:
            raise ValueError("知识库不存在")
        return self._retrieval_config_from_json(row["retrieval_config_json"])

    def update_collection_retrieval_config(
        self, collection_id: str, updates: Mapping[str, object]
    ) -> KnowledgeCollection:
        self._validate_collection_id(collection_id)
        normalised_updates = normalise_retrieval_config(updates)
        if not normalised_updates:
            raise ValueError("至少提供一项检索策略")
        try:
            with self._write_transaction() as connection:
                row = connection.execute("SELECT * FROM knowledge_collections WHERE id=?", (collection_id,)).fetchone()
                if row is None:
                    raise ValueError("知识库不存在")
                config = self._retrieval_config_from_json(row["retrieval_config_json"])
                config.update(normalised_updates)
                connection.execute(
                    "UPDATE knowledge_collections SET retrieval_config_json=? WHERE id=?",
                    (json.dumps(config, ensure_ascii=False, sort_keys=True), collection_id),
                )
                row = connection.execute("SELECT * FROM knowledge_collections WHERE id=?", (collection_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to update knowledge collection retrieval config") from exc
        return self._collection_from_row(row)

    @staticmethod
    def _retrieval_config_from_json(value: object) -> dict[str, int | float]:
        try:
            parsed = json.loads(value) if isinstance(value, str) else {}
        except json.JSONDecodeError as exc:
            raise SqliteKnowledgeRepositoryError("invalid knowledge collection retrieval config") from exc
        try:
            return normalise_retrieval_config(parsed)
        except ValueError as exc:
            raise SqliteKnowledgeRepositoryError("invalid knowledge collection retrieval config") from exc

    @classmethod
    def _collection_from_row(cls, row: sqlite3.Row) -> KnowledgeCollection:
        values = dict(row)
        values["retrieval_config"] = cls._retrieval_config_from_json(values.pop("retrieval_config_json", "{}"))
        return KnowledgeCollection(**values)

    @staticmethod
    def _validate_collection_id(collection_id: object) -> None:
        if not isinstance(collection_id, str) or not re.fullmatch(r"collection-(?:general|[0-9a-f]{32})", collection_id):
            raise ValueError("invalid knowledge collection id")

    def _collection_exists(self, connection: sqlite3.Connection, collection_id: str) -> None:
        if connection.execute("SELECT 1 FROM knowledge_collections WHERE id=?", (collection_id,)).fetchone() is None:
            raise ValueError("知识库不存在")

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> KnowledgeDocument:
        return KnowledgeDocument(**dict(row))

    @staticmethod
    def _normalise_chunks(document_id: str, chunks: list[ChunkDraft | ChunkGroup | KnowledgeChunk]) -> list[KnowledgeChunk]:
        if not isinstance(chunks, list):
            raise ValueError("chunks must be a list")
        normalised: list[KnowledgeChunk] = []
        counter = 0
        for chunk in chunks:
            if isinstance(chunk, ChunkDraft):
                normalised.append(KnowledgeChunk.new(document_id, counter, chunk.content, location=chunk.location))
                counter += 1
            elif isinstance(chunk, ChunkGroup):
                parent = KnowledgeChunk.new(document_id, counter, chunk.parent.content, location=chunk.parent.location)
                counter += 1
                normalised.append(parent)
                for child in chunk.children:
                    normalised.append(KnowledgeChunk.new(document_id, counter, child.content, location=child.location, parent_id=parent.id))
                    counter += 1
            elif isinstance(chunk, KnowledgeChunk):
                if chunk.document_id != document_id:
                    raise ValueError("chunk belongs to another document")
                normalised.append(chunk)
                counter = max(counter, chunk.ordinal + 1)
            else:
                raise ValueError("chunks must contain ChunkDraft, ChunkGroup or KnowledgeChunk")
        return normalised

    @staticmethod
    def _legacy_marker(entry: KnowledgeEntry) -> str:
        # The JSON entry id is immutable; source URLs can be edited between runs.
        return f"legacy:{entry.id}"

    @classmethod
    def _legacy_original_name(cls, entry: KnowledgeEntry) -> str:
        marker = cls._legacy_marker(entry)
        return f"{marker}\n{entry.source_url}" if entry.source_url else marker

    @staticmethod
    def _validate_document_id(document_id: object) -> None:
        if not isinstance(document_id, str) or len(document_id) != 36 or not document_id.startswith("doc-"):
            raise ValueError("invalid knowledge document id")
        try:
            int(document_id[4:], 16)
        except ValueError as exc:
            raise ValueError("invalid knowledge document id") from exc

    @staticmethod
    def _validate_chunk_id(chunk_id: object) -> None:
        if not isinstance(chunk_id, str) or not re.fullmatch(r"chunk-[0-9a-f]{32}", chunk_id):
            raise ValueError("invalid knowledge chunk id")

    @staticmethod
    def _validate_text(value: object, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-blank")

    @staticmethod
    def _validate_limit(limit: object) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")

    @staticmethod
    def _validate_embedding(chunk_id: object, vector: object) -> tuple[str, list[float], int]:
        if not isinstance(chunk_id, str) or not chunk_id.startswith("chunk-") or len(chunk_id) != 38:
            raise ValueError("invalid knowledge chunk id")
        try:
            int(chunk_id[6:], 16)
        except ValueError as exc:
            raise ValueError("invalid knowledge chunk id") from exc
        if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence) or not vector:
            raise ValueError("embedding vector must be non-empty")
        values = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("embedding vector must be finite")
        return chunk_id, values, len(values)

    @staticmethod
    def _fts_text(content: str) -> str:
        """Add individual CJK characters so FTS5 can match Chinese substrings."""
        cjk_characters = [character for character in content if "\u4e00" <= character <= "\u9fff"]
        return content if not cjk_characters else f"{content} {' '.join(cjk_characters)}"

    @staticmethod
    def _fts_query(query: str) -> str:
        """Convert user text into literal FTS5 terms, never FTS syntax."""
        terms: list[str] = []
        for token in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", query):
            if "\u4e00" <= token[0] <= "\u9fff" and len(token) > 1:
                terms.extend(f"{left} {right}" for left, right in zip(token, token[1:]))
            else:
                terms.append(token)
        if not terms:
            raise ValueError("query must contain searchable text")
        return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


class _ImmediateTransaction:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
        return False
