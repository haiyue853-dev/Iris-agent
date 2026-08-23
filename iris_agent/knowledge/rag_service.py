"""Local document ingestion and hybrid retrieval for the RAG knowledge base."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.storage import AttachmentFile
from iris_agent.knowledge.chunker import chunk_text
from iris_agent.knowledge.documents import KnowledgeDocument
from iris_agent.knowledge.embedder import EmbeddingError, OllamaEmbedder
from iris_agent.knowledge.sqlite_repository import KeywordSearchHit, SqliteKnowledgeRepository


@dataclass(frozen=True, slots=True)
class RagSearchHit:
    document_id: str
    chunk_id: str
    title: str
    content: str
    location: str | None
    score: float

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "chunk_id": self.chunk_id, "title": self.title,
                "content": self.content, "location": self.location, "score": round(self.score, 4)}


class RagKnowledgeService:
    def __init__(self, repository: SqliteKnowledgeRepository, *, embedder: OllamaEmbedder | None,
                 files_directory: Path, chunk_target_chars: int, chunk_overlap_chars: int,
                 embedding_batch_size: int, retrieval_limit: int, max_context_chars: int,
                 minimum_relevance_score: float, max_file_bytes: int, max_total_bytes: int,
                 max_document_count: int, allowed_extensions: tuple[str, ...]):
        self.repository, self.embedder = repository, embedder
        self.files_directory = files_directory
        self.chunk_target_chars, self.chunk_overlap_chars = chunk_target_chars, chunk_overlap_chars
        self.embedding_batch_size, self.retrieval_limit = embedding_batch_size, retrieval_limit
        self.max_context_chars, self.minimum_relevance_score = max_context_chars, minimum_relevance_score
        self.max_file_bytes, self.max_total_bytes, self.max_document_count = max_file_bytes, max_total_bytes, max_document_count
        self.allowed_extensions = frozenset(item.lower() for item in allowed_extensions)
        self.files_directory.mkdir(parents=True, exist_ok=True)

    def list_documents(self) -> list[KnowledgeDocument]:
        return self.repository.list_documents()

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self.repository.get_document(document_id)

    def delete_document(self, document_id: str) -> bool:
        return self.repository.delete_document(document_id) is not None

    def graph(self, topic: str | None = None) -> dict:
        nodes, edges = self.repository.graph(topic)
        return {"nodes": [{"id": node.id, "label": node.label, "kind": node.kind, "document_count": node.document_count} for node in nodes],
                "edges": [{"source": edge.source, "target": edge.target, "relation": edge.relation, "document_id": edge.document_id} for edge in edges]}

    def topics(self) -> list[str]:
        return [node.label for node in self.repository.graph(limit=100)[0] if node.kind == "topic"]

    def add_text(self, title: str, content: str, *, source_type: str = "manual", original_name: str | None = None) -> KnowledgeDocument:
        if not isinstance(content, str) or not content.strip(): raise ValueError("知识内容不能为空")
        return self._store(title, content, source_type, "text/plain", len(content.encode("utf-8")), original_name)

    def add_upload(self, title: str, original_name: str, content: bytes, media_type: str | None = None) -> KnowledgeDocument:
        suffix = Path(original_name).suffix.lower()
        if suffix not in self.allowed_extensions: raise ValueError("不支持该知识库文件类型")
        if not content or len(content) > self.max_file_bytes: raise ValueError("知识库文件超过大小限制")
        if len(self.list_documents()) >= self.max_document_count: raise ValueError("知识库文档数量已达上限")
        if sum(item.size_bytes for item in self.list_documents()) + len(content) > self.max_total_bytes: raise ValueError("知识库文件总大小已达上限")
        target = self.files_directory / f"{uuid4().hex}{suffix}"
        target.write_bytes(content)
        try:
            import os
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            attachment = AttachmentFile(target, descriptor, original_name)
            try:
                extraction = LocalAttachmentExtractor(max_chars=2_000_000).extract(attachment)
            finally:
                attachment.close()
            return self._store(title or original_name, extraction.text, "upload", media_type, len(content), original_name,
                               ", ".join(source.location for source in extraction.sources if source.location) or None)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def search(self, query: str, limit: int | None = None) -> list[RagSearchHit]:
        if not isinstance(query, str) or not query.strip(): return []
        amount = limit or self.retrieval_limit
        keyword = self.repository.keyword_search(query, amount * 3)
        scores: dict[str, float] = {}; records: dict[str, RagSearchHit] = {}
        for rank, hit in enumerate(keyword, 1):
            self._add_hit(records, scores, hit.chunk_id, hit.document_id, hit.title, hit.content, hit.location, 1.0 / (60 + rank))
        if self.embedder is not None:
            try:
                vector = self.embedder.embed([query])[0]
                ranked = sorted(((self._cosine(vector, candidate.vector), candidate) for candidate in self.repository.embedding_candidates()), key=lambda pair: -pair[0])
                for rank, (similarity, candidate) in enumerate(ranked[:amount * 3], 1):
                    if similarity > 0:
                        self._add_hit(records, scores, candidate.chunk_id, candidate.document_id, candidate.title, candidate.content, candidate.location, 1.0 / (60 + rank))
            except (EmbeddingError, OSError, ValueError):
                pass
        return [RagSearchHit(records[key].document_id, records[key].chunk_id, records[key].title,
                             records[key].content, records[key].location, scores[key])
                for key in sorted(records, key=lambda item: -scores[item])[:amount]]

    def context_for(self, query: str) -> tuple[str, list[dict]]:
        hits = self.search(query)
        parts: list[str] = []; citations: list[dict] = []; used = 0
        for index, hit in enumerate(hits, 1):
            text = hit.content.strip()
            remaining = self.max_context_chars - used
            if remaining <= 0: break
            text = text[:remaining]
            parts.append(f"[{index}] 《{hit.title}》{('（' + hit.location + '）') if hit.location else ''}\n{text}")
            citations.append({"index": index, **hit.to_dict()}); used += len(text)
        if not parts: return "", []
        return "[本地知识库检索结果]\n" + "\n\n".join(parts) + "\n回答涉及上述内容时请用 [1]、[2] 标明来源。", citations

    def _store(self, title: str, content: str, source_type: str, media_type: str | None, size_bytes: int, original_name: str | None, location: str | None = None) -> KnowledgeDocument:
        document = KnowledgeDocument.new(title=title, source_type=source_type, media_type=media_type,
                                         size_bytes=size_bytes, original_name=original_name, status="ready")
        drafts = chunk_text(content, target_chars=self.chunk_target_chars, overlap_chars=self.chunk_overlap_chars, location=location)
        self.repository.save_document_with_chunks(document, drafts)
        entities, relations = self._extract_graph(title, content)
        self.repository.replace_document_graph(document.id, entities, relations)
        if self.embedder is not None and drafts:
            try:
                vectors = self.embedder.embed([item.content for item in drafts])
                chunks = self.repository.chunks_for_document(document.id)
                self.repository.save_embeddings(document.id, self.embedder.model, zip((item.id for item in chunks), vectors))
            except (EmbeddingError, OSError, ValueError):
                pass
        return document

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right): return 0.0
        denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0

    @staticmethod
    def _add_hit(records, scores, chunk_id, document_id, title, content, location, score):
        records.setdefault(chunk_id, RagSearchHit(document_id, chunk_id, title, content, location, 0.0)); scores[chunk_id] = scores.get(chunk_id, 0.0) + score

    @staticmethod
    def _extract_graph(title: str, content: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        """Local deterministic extraction: titles are topics; repeated terms become entities."""
        topic = title.strip()[:120]
        candidates = re.findall(r"[A-Za-z][A-Za-z0-9+.#_-]{1,40}|[\u4e00-\u9fff]{2,10}", content)
        seen: list[str] = []
        for value in candidates:
            value = value.strip("，。；：、（）()[]【】")
            if value and value != topic and value not in seen: seen.append(value)
            if len(seen) == 12: break
        entities = [(topic, "topic"), *[(value, "entity") for value in seen]]
        return entities, [(topic, value, "包含") for value in seen]
