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

from iris_agent.knowledge.chunker import ChunkDraft
from iris_agent.knowledge.documents import KnowledgeChunk, KnowledgeDocument
from iris_agent.knowledge.models import KnowledgeEntry
from iris_agent.knowledge.repository import KnowledgeRepository


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
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                    USING fts5(chunk_id UNINDEXED, title, content);
                    CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise SqliteKnowledgeRepositoryError("unable to initialise knowledge database") from exc

    def save_document_with_chunks(
        self, document: KnowledgeDocument, chunks: list[ChunkDraft | KnowledgeChunk]
    ) -> None:
        if not isinstance(document, KnowledgeDocument):
            raise ValueError("document must be a KnowledgeDocument")
        persisted_chunks = self._normalise_chunks(document.id, chunks)
        try:
            with self._write_transaction() as connection:
                self._insert_document_with_chunks(connection, document, persisted_chunks)
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

    def list_documents(self) -> list[KnowledgeDocument]:
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT * FROM documents ORDER BY created_at, id").fetchall()
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to list knowledge documents") from exc
        return [self._document_from_row(row) for row in rows]

    def keyword_search(self, query: str, limit: int) -> list[KeywordSearchHit]:
        self._validate_text(query, "query")
        self._validate_limit(limit)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """SELECT f.chunk_id, c.document_id, d.title, c.content, c.location,
                              -bm25(chunks_fts) AS score
                       FROM chunks_fts AS f
                       JOIN chunks AS c ON c.id = f.chunk_id
                       JOIN documents AS d ON d.id = c.document_id
                       WHERE chunks_fts MATCH ?
                       ORDER BY score DESC, c.ordinal ASC
                       LIMIT ?""",
                    (self._fts_query(query), limit),
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
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        except sqlite3.Error as exc:
            raise SqliteKnowledgeRepositoryError("unable to delete knowledge document") from exc
        return self._document_from_row(row)

    def save_embeddings(self, document_id: str, model: str, mappings: EmbeddingMappings) -> None:
        self._validate_document_id(document_id)
        self._validate_text(model, "embedding model")
        items = list(mappings.items()) if isinstance(mappings, Mapping) else list(mappings)
        normalised = [(self._validate_embedding(chunk_id, vector)) for chunk_id, vector in items]
        try:
            with self._write_transaction() as connection:
                if connection.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
                    raise ValueError("unknown knowledge document")
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
                        self._insert_document_with_chunks(connection, document, chunks)
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
        self, connection: sqlite3.Connection, document: KnowledgeDocument, chunks: list[KnowledgeChunk]
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
                """INSERT INTO chunks (id, document_id, ordinal, content, location, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk.id, chunk.document_id, chunk.ordinal, chunk.content, chunk.location, chunk.content_hash),
            )
            connection.execute(
                "INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)",
                (chunk.id, self._fts_text(document.title), self._fts_text(chunk.content)),
            )

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> KnowledgeDocument:
        return KnowledgeDocument(**dict(row))

    @staticmethod
    def _normalise_chunks(document_id: str, chunks: list[ChunkDraft | KnowledgeChunk]) -> list[KnowledgeChunk]:
        if not isinstance(chunks, list):
            raise ValueError("chunks must be a list")
        normalised: list[KnowledgeChunk] = []
        for ordinal, chunk in enumerate(chunks):
            if isinstance(chunk, ChunkDraft):
                normalised.append(KnowledgeChunk.new(document_id, ordinal, chunk.content, location=chunk.location))
            elif isinstance(chunk, KnowledgeChunk):
                if chunk.document_id != document_id:
                    raise ValueError("chunk belongs to another document")
                normalised.append(chunk)
            else:
                raise ValueError("chunks must contain ChunkDraft or KnowledgeChunk")
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
        terms = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", query)
        if not terms:
            raise ValueError("query must contain searchable text")
        return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


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
