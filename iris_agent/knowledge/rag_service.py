"""Local document ingestion and hybrid retrieval for the RAG knowledge base."""

from __future__ import annotations

import math
import re
import time
import json
import threading
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

import httpx

from iris_agent.knowledge.chunker import ChunkGroup, build_chunks, chunk_text
from iris_agent.knowledge.documents import KnowledgeDocument
from iris_agent.knowledge.embedder import EmbeddingError, OllamaEmbedder
from iris_agent.knowledge.extractor import OllamaGraphExtractor, canonical_graph_label, canonical_graph_relation
from iris_agent.knowledge.semantic_splitter import LocalSemanticSplitter, SemanticSplitError
from iris_agent.knowledge.mindmap import build_fallback_mindmap
from iris_agent.knowledge.parsing import OllamaImageDescriber, ParsingError, parse_document
from iris_agent.knowledge.query_rewriter import expand_retrieval_query
from iris_agent.knowledge.reranking import Reranker, build_reranker
from iris_agent.knowledge.runtime_config import normalise_runtime_config, save_runtime_config
from iris_agent.knowledge.sqlite_repository import (
    KeywordSearchHit,
    SqliteKnowledgeRepository,
    SqliteKnowledgeRepositoryError,
)

_PARSE_MAX_CHARS = 2_000_000


@dataclass(frozen=True, slots=True)
class RagSearchHit:
    document_id: str
    chunk_id: str
    title: str
    content: str
    location: str | None
    score: float
    keyword_score: float = 0.0
    vector_score: float = 0.0
    reranker_score: float | None = None
    graph_score: float = 0.0
    routes: tuple[str, ...] = ()
    collection_id: str | None = None
    collection_name: str | None = None

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "chunk_id": self.chunk_id, "title": self.title,
                "content": self.content, "location": self.location, "score": round(self.score, 4),
                "keyword_score": round(self.keyword_score, 4), "vector_score": round(self.vector_score, 4),
                "reranker_score": None if self.reranker_score is None else round(self.reranker_score, 4),
                "graph_score": round(self.graph_score, 4), "routes": list(self.routes),
                "collection_id": self.collection_id, "collection_name": self.collection_name}


class RagKnowledgeService:
    def __init__(self, repository: SqliteKnowledgeRepository, *, embedder: OllamaEmbedder | None,
                 files_directory: Path, chunk_target_chars: int, chunk_overlap_chars: int,
                 embedding_batch_size: int, retrieval_limit: int, max_context_chars: int,
                 minimum_relevance_score: float, max_file_bytes: int, max_total_bytes: int,
                 max_document_count: int, allowed_extensions: tuple[str, ...], graph_extractor: OllamaGraphExtractor | None = None,
                 semantic_splitter: LocalSemanticSplitter | None = None,
                 reranker: Reranker | None = None, reranker_candidates: int = 15,
                 rrf_k: int = 60, retrieval_candidate_multiplier: int = 3,
                 parent_chunk_target_chars: int | None = None, child_chunk_target_chars: int | None = None,
                 child_chunk_overlap_chars: int | None = None,
                 image_describer: Callable[[bytes, str], str] | None = None,
                 image_parser: OllamaImageDescriber | None = None,
                 model_config: dict | None = None, runtime_config_path: Path | None = None,
                 reranker_api_key: str = "", embedding_timeout_seconds: float = 60,
                 graph_timeout_seconds: float = 120, semantic_split_timeout_seconds: float = 180,
                 image_timeout_seconds: float = 120,
                 reranker_timeout_seconds: float = 60):
        self.repository, self.embedder = repository, embedder
        self.files_directory = files_directory
        self.chunk_target_chars, self.chunk_overlap_chars = chunk_target_chars, chunk_overlap_chars
        self.parent_chunk_target_chars = parent_chunk_target_chars
        self.child_chunk_target_chars, self.child_chunk_overlap_chars = child_chunk_target_chars, child_chunk_overlap_chars
        self.embedding_batch_size, self.retrieval_limit = embedding_batch_size, retrieval_limit
        self.max_context_chars, self.minimum_relevance_score = max_context_chars, minimum_relevance_score
        self.max_file_bytes, self.max_total_bytes, self.max_document_count = max_file_bytes, max_total_bytes, max_document_count
        self.allowed_extensions = frozenset(item.lower() for item in allowed_extensions)
        self.graph_extractor = graph_extractor
        self.semantic_splitter = semantic_splitter
        self._image_parser = image_parser
        self.image_describer = image_parser.describe if image_parser is not None else image_describer
        self.reranker, self.reranker_candidates = reranker, max(1, reranker_candidates)
        self.rrf_k = max(1, rrf_k)
        self.retrieval_candidate_multiplier = max(1, retrieval_candidate_multiplier)
        self.evaluation_directory = files_directory.parent / "evaluation"
        self.evaluation_directory.mkdir(parents=True, exist_ok=True)
        self.files_directory.mkdir(parents=True, exist_ok=True)
        self._ingest_lock = threading.RLock()
        self._evaluation_lock = threading.RLock()
        self._index_progress: dict[str, dict[str, object]] = {}
        inferred_provider = (
            "api" if reranker is not None and reranker.__class__.__name__ == "HttpApiReranker"
            else "fastembed" if reranker is not None and reranker.__class__.__name__ == "FastEmbedReranker"
            else "ollama" if reranker is not None else "none"
        )
        inferred_image = image_parser or getattr(image_describer, "__self__", None)
        defaults = {
            "embedding_enabled": embedder is not None,
            "embedding_model": str(getattr(embedder, "model", "bge-m3")),
            "embedding_base_url": str(getattr(embedder, "base_url", "http://localhost:11434")),
            "semantic_split_enabled": semantic_splitter is not None,
            "semantic_split_model": str(getattr(semantic_splitter, "model", "bge-m3")),
            "semantic_split_base_url": str(getattr(semantic_splitter, "base_url", "http://localhost:11434")),
            "graph_enabled": graph_extractor is not None,
            "graph_model": str(getattr(graph_extractor, "model", "deepseek-r1:8b")),
            "graph_base_url": str(getattr(graph_extractor, "base_url", "http://localhost:11434")),
            "image_enabled": self.image_describer is not None,
            "image_model": str(getattr(inferred_image, "model", "qwen2.5vl:7b")),
            "image_base_url": str(getattr(inferred_image, "base_url", "http://localhost:11434")),
            "reranker_enabled": reranker is not None,
            "reranker_provider": inferred_provider,
            "reranker_model": str(getattr(reranker, "model", "deepseek-r1:8b")),
            "reranker_base_url": str(getattr(reranker, "base_url", getattr(reranker, "endpoint", "http://localhost:11434"))).removesuffix("/rerank"),
            "mmr_relevance_weight": 0.7,
        }
        self._model_config = normalise_runtime_config(model_config or defaults, defaults)
        self._mmr_relevance_weight = float(self._model_config["mmr_relevance_weight"])
        self._runtime_config_path = runtime_config_path
        self._reranker_api_key = reranker_api_key
        self._model_timeouts = {
            "embedding": embedding_timeout_seconds, "graph": graph_timeout_seconds,
            "semantic_split": semantic_split_timeout_seconds,
            "image": image_timeout_seconds, "reranker": reranker_timeout_seconds,
        }
        self._model_health: dict[str, dict[str, object]] = {}
        self._indexer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iris-knowledge-index")
        if hasattr(self.repository, "backfill_vector_index"):
            self._indexer.submit(self.repository.backfill_vector_index)
        for document in self.repository.list_documents():
            if document.status in {"queued", "indexing"}:
                self._indexer.submit(self._index_document, document.id)

    def close(self) -> None:
        self._indexer.shutdown(wait=False, cancel_futures=False)
        for adapter in (self.embedder, self.semantic_splitter, self.graph_extractor, self._image_parser, self.reranker):
            self._close_adapter(adapter)

    @staticmethod
    def _close_adapter(adapter: object | None) -> None:
        if adapter is None:
            return
        close = getattr(adapter, "close", None)
        if callable(close):
            close()
            return
        client = getattr(adapter, "_client", None) or getattr(adapter, "client", None)
        client_close = getattr(client, "close", None)
        if callable(client_close):
            client_close()

    def _runtime_components(self) -> list[dict[str, object]]:
        definitions = (
            ("embedding", "向量模型", "ollama"),
            ("graph", "图谱模型", "ollama"),
            ("image", "视觉解析", "ollama"),
            ("reranker", "重排模型", str(self._model_config["reranker_provider"])),
        )
        components = []
        for key, label, provider in definitions:
            enabled = bool(self._model_config[f"{key}_enabled"])
            health = self._model_health.get(key, {})
            components.append({
                "key": key, "label": label, "enabled": enabled,
                "provider": provider, "model": self._model_config[f"{key}_model"],
                "base_url": self._model_config[f"{key}_base_url"],
                "status": health.get("status", "untested" if enabled else "disabled"),
                "message": health.get("message", "尚未测试" if enabled else "已停用"),
                "latency_ms": health.get("latency_ms"),
            })
        return components

    def model_runtime(self) -> dict[str, object]:
        return {"config": dict(self._model_config), "components": self._runtime_components()}

    def update_model_runtime(self, changes: dict) -> dict[str, object]:
        if not isinstance(changes, dict):
            raise ValueError("RAG 运行配置必须是对象")
        previous = dict(self._model_config)
        updated = normalise_runtime_config({**previous, **changes}, previous)
        new_embedder = OllamaEmbedder(
            model=str(updated["embedding_model"]), base_url=str(updated["embedding_base_url"]),
            timeout=self._model_timeouts["embedding"],
        ) if updated["embedding_enabled"] else None
        new_semantic_splitter = LocalSemanticSplitter(OllamaEmbedder(
            model=updated["semantic_split_model"], base_url=updated["semantic_split_base_url"],
            timeout=self._model_timeouts["semantic_split"],
        ), owns_embedder=True) if updated["semantic_split_enabled"] else None
        new_graph = OllamaGraphExtractor(
            model=updated["graph_model"], base_url=updated["graph_base_url"],
            timeout=self._model_timeouts["graph"],
        ) if updated["graph_enabled"] else None
        new_image = OllamaImageDescriber(
            model=updated["image_model"], base_url=updated["image_base_url"],
            timeout=self._model_timeouts["image"],
        ) if updated["image_enabled"] else None
        new_reranker = build_reranker(
            updated["reranker_provider"] if updated["reranker_enabled"] else "none",
            model=updated["reranker_model"], base_url=updated["reranker_base_url"],
            api_key=self._reranker_api_key, timeout=self._model_timeouts["reranker"],
        )
        adapters = (new_embedder, new_semantic_splitter, new_graph, new_image, new_reranker)
        try:
            if self._runtime_config_path is not None:
                save_runtime_config(self._runtime_config_path, updated, previous)
        except Exception:
            for adapter in adapters:
                self._close_adapter(adapter)
            raise
        with self._ingest_lock:
            old_adapters = (self.embedder, self.semantic_splitter, self.graph_extractor, self._image_parser, self.reranker)
            self.embedder, self.semantic_splitter, self.graph_extractor, self._image_parser, self.reranker = adapters
            self.image_describer = new_image.describe if new_image is not None else None
            self._model_config = updated
            self._mmr_relevance_weight = float(updated["mmr_relevance_weight"])
            self._model_health = {}
        for adapter in old_adapters:
            self._close_adapter(adapter)
        requires_reindex = any(previous[key] != updated[key] for key in (
            "embedding_enabled", "embedding_model", "embedding_base_url",
            "semantic_split_enabled", "semantic_split_model", "semantic_split_base_url",
        ))
        return {**self.model_runtime(), "requires_reindex": requires_reindex}

    @staticmethod
    def _ollama_has_model(payload: object, model: str) -> bool:
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return False
        requested = model.casefold()
        requested_base = requested.split(":", 1)[0]
        for item in payload["models"]:
            name = str(item.get("name") or item.get("model") or "").casefold() if isinstance(item, dict) else ""
            if name == requested or name.split(":", 1)[0] == requested_base:
                return True
        return False

    def test_model_runtime(self, component: str | None = None) -> dict[str, object]:
        keys = [component] if component else ["embedding", "graph", "image", "reranker"]
        if any(key not in {"embedding", "graph", "image", "reranker"} for key in keys):
            raise ValueError("未知的 RAG 模型组件")
        ollama_cache: dict[str, tuple[object | None, Exception | None, int]] = {}
        for key in keys:
            enabled = bool(self._model_config[f"{key}_enabled"])
            if not enabled:
                self._model_health[key] = {"status": "disabled", "message": "已停用", "latency_ms": None}
                continue
            started = time.perf_counter()
            try:
                provider = self._model_config["reranker_provider"] if key == "reranker" else "ollama"
                if provider in {"api", "fastembed"}:
                    if self.reranker is None:
                        raise ValueError("重排器尚未初始化")
                    scores = self.reranker.score("连接测试", [("health", "连接测试文档")])
                    if "health" not in scores:
                        raise ValueError("重排接口未返回有效分数")
                else:
                    base_url = str(self._model_config[f"{key}_base_url"])
                    if base_url not in ollama_cache:
                        request_started = time.perf_counter()
                        try:
                            response = httpx.get(
                                f"{base_url}/api/tags",
                                timeout=min(float(self._model_timeouts[key]), 10.0), trust_env=False,
                            )
                            response.raise_for_status()
                            ollama_cache[base_url] = (response.json(), None, round((time.perf_counter() - request_started) * 1000))
                        except Exception as exc:
                            ollama_cache[base_url] = (None, exc, round((time.perf_counter() - request_started) * 1000))
                    payload, request_error, cached_latency = ollama_cache[base_url]
                    if request_error is not None:
                        raise request_error
                    if not self._ollama_has_model(payload, str(self._model_config[f"{key}_model"])):
                        raise ValueError(f"模型 {self._model_config[f'{key}_model']} 未安装")
                    if key == "reranker":
                        if self.reranker is None:
                            raise ValueError("重排器尚未初始化")
                        scores = self.reranker.score("连接测试", [("health", "连接测试文档")])
                        if "health" not in scores:
                            raise ValueError("重排模型未返回有效分数")
                elapsed = (round((time.perf_counter() - started) * 1000) if key == "reranker"
                           else cached_latency if provider == "ollama" else round((time.perf_counter() - started) * 1000))
                self._model_health[key] = {"status": "connected", "message": "服务可用，模型已安装", "latency_ms": elapsed}
            except Exception as exc:
                elapsed = round((time.perf_counter() - started) * 1000)
                message = (
                    "无法连接 Ollama 服务，请确认服务已启动且地址正确"
                    if provider == "ollama" and isinstance(exc, httpx.RequestError)
                    else str(exc)[:240]
                )
                self._model_health[key] = {"status": "failed", "message": message, "latency_ms": elapsed}
        selected = set(keys)
        return {"components": [item for item in self._runtime_components() if item["key"] in selected]}

    def _set_index_progress(self, document_id: str, stage: str, message: str, *, failed_stage: str | None = None) -> None:
        item: dict[str, object] = {
            "document_id": document_id,
            "stage": stage,
            "message": message[:500],
            "updated_at": time.time(),
        }
        if failed_stage:
            item["failed_stage"] = failed_stage
        with self._ingest_lock:
            self._index_progress[document_id] = item

    def index_progress(self) -> dict[str, list[dict[str, object]]]:
        documents = {document.id: document for document in self.repository.list_documents()}
        with self._ingest_lock:
            items = [dict(item) for document_id, item in self._index_progress.items() if document_id in documents]
        known = {str(item["document_id"]) for item in items}
        for document in documents.values():
            if document.id in known:
                continue
            stage = "completed" if document.status == "ready" else "failed" if document.status == "failed" else document.status
            items.append({
                "document_id": document.id,
                "stage": stage,
                "message": document.error_message or ("索引已完成" if stage == "completed" else "等待建立索引"),
                "updated_at": document.updated_at,
            })
        return {"items": sorted(items, key=lambda item: float(item["updated_at"]), reverse=True)}

    def _build_chunks(self, text: str, location: str | None, *, title: str | None = None) -> list:
        if self.semantic_splitter is not None and title:
            try:
                semantic_chunks = self.semantic_splitter.split(
                    title, text, target_chars=self.parent_chunk_target_chars or self.chunk_target_chars,
                )
                if semantic_chunks:
                    return self._expand_semantic_chunks(semantic_chunks, location)
            except (SemanticSplitError, OSError, ValueError):
                pass
        return build_chunks(
            text, location=location, target_chars=self.chunk_target_chars, overlap_chars=self.chunk_overlap_chars,
            parent_target_chars=self.parent_chunk_target_chars,
            child_target_chars=self.child_chunk_target_chars,
            child_overlap_chars=self.child_chunk_overlap_chars,
        )

    def _parse_source_file(self, path: Path) -> tuple[str, str | None]:
        text, location, _ = self._parse_source_file_content(path)
        return text, location

    def _parse_source_file_content(self, path: Path, *, title: str | None = None) -> tuple[str, str | None, list]:
        parsed = parse_document(
            path.suffix.lower(), path.read_bytes(), name=path.name,
            image_describer=self.image_describer,
        )
        sections: list[tuple[str, str | None]] = []
        remaining = _PARSE_MAX_CHARS
        for section in parsed.sections:
            if remaining <= 0:
                break
            text = section.text[:remaining]
            remaining -= len(text)
            if text.strip():
                sections.append((text, section.location))
        text = "\n\n".join(section[0] for section in sections)
        if not text.strip():
            raise ParsingError("文档未包含可提取文本")
        location = ", ".join(dict.fromkeys(section[1] for section in sections if section[1])) or None
        if self.semantic_splitter is not None and title:
            try:
                semantic_chunks = self.semantic_splitter.split(
                    title, text, target_chars=self.parent_chunk_target_chars or self.chunk_target_chars,
                )
                if semantic_chunks:
                    return text, location, self._expand_semantic_chunks(semantic_chunks, location)
            except (SemanticSplitError, OSError, ValueError):
                pass
        chunks = [
            chunk
            for section_text, section_location in sections
            for chunk in self._build_chunks(section_text, section_location)
        ]
        return text, location, chunks

    def _expand_semantic_chunks(self, chunks: list, fallback_location: str | None) -> list:
        expanded: list = []
        for chunk in chunks:
            expanded.extend(build_chunks(
                chunk.content, location=chunk.location or fallback_location,
                target_chars=self.chunk_target_chars, overlap_chars=self.chunk_overlap_chars,
                parent_target_chars=self.parent_chunk_target_chars,
                child_target_chars=self.child_chunk_target_chars,
                child_overlap_chars=self.child_chunk_overlap_chars,
            ))
        return expanded

    def list_documents(self, collection_id: str | None = None) -> list[KnowledgeDocument]:
        return self.repository.list_documents(collection_id)

    def list_collections(self): return self.repository.list_collections()
    def create_collection(self, name: str, description: str | None = None): return self.repository.create_collection(name, description)
    def _default_retrieval_config(self) -> dict[str, int | float]:
        return {
            "top_k": self.retrieval_limit,
            "candidate_multiplier": self.retrieval_candidate_multiplier,
            "minimum_relevance_score": self.minimum_relevance_score,
            "mmr_relevance_weight": self._mmr_relevance_weight,
        }

    def collection_retrieval_config(self, collection_id: str) -> dict[str, int | float]:
        config = self._default_retrieval_config()
        config.update(self.repository.collection_retrieval_config(collection_id))
        return config

    def update_collection_retrieval_config(self, collection_id: str, updates: dict[str, object]) -> dict[str, int | float]:
        self.repository.update_collection_retrieval_config(collection_id, updates)
        return self.collection_retrieval_config(collection_id)
    def delete_collection(self, collection_id: str) -> bool:
        documents = self.repository.list_documents(collection_id)
        deleted = self.repository.delete_collection(collection_id)
        if deleted:
            for document in documents:
                for source_file in self.files_directory.glob(f"{document.id}.*"):
                    try:
                        source_file.unlink(missing_ok=True)
                    except OSError:
                        pass
        return deleted
    def rename_collection(self, collection_id: str, name: str): return self.repository.rename_collection(collection_id, name)

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self.repository.get_document(document_id)

    def document_source_path(self, document_id: str) -> Path | None:
        document = self.repository.get_document(document_id)
        if document is None or document.source_type != "upload":
            return None
        return next(self.files_directory.glob(f"{document.id}.*"), None)

    def document_mindmap(self, document_id: str) -> dict:
        document = self.repository.get_document(document_id)
        if document is None:
            raise ValueError("知识资料不存在")
        return {"document_id": document_id, "title": document.title, "nodes": [node.to_dict() for node in self.repository.document_mindmap(document_id)]}

    def document_detail(self, document_id: str) -> dict | None:
        document = self.repository.get_document(document_id)
        if document is None: return None
        chunks = self.repository.chunks_for_document(document_id)
        return {**document.to_dict(), "chunks": [item.to_dict() for item in chunks], "index_stats": {"chunk_count": len(chunks), "embedding_count": self.repository.embedding_count(document_id), "graph_node_count": self.repository.graph_node_count(document_id), "graph_edge_count": self.repository.graph_edge_count(document_id)}}

    def update_chunk(self, chunk_id: str, content: str, location: str | None = None) -> dict:
        chunk = self.repository.update_chunk(chunk_id, content, location)
        embedding_updated = self._reembed_edited_chunk(chunk)
        return {"chunk": chunk.to_dict(), "revisions": self.repository.chunk_revisions(chunk_id), "embedding_updated": embedding_updated}

    def chunk_revisions(self, chunk_id: str, limit: int = 20) -> dict:
        return {"chunk_id": chunk_id, "revisions": self.repository.chunk_revisions(chunk_id, limit)}

    def restore_chunk_revision(self, chunk_id: str, revision_id: str) -> dict:
        chunk = self.repository.restore_chunk_revision(chunk_id, revision_id)
        embedding_updated = self._reembed_edited_chunk(chunk)
        return {"chunk": chunk.to_dict(), "revisions": self.repository.chunk_revisions(chunk_id), "embedding_updated": embedding_updated}

    def _reembed_edited_chunk(self, chunk) -> bool:
        if self.embedder is None:
            return False
        document_chunks = self.repository.chunks_for_document(chunk.document_id)
        if any(item.parent_id == chunk.id for item in document_chunks):
            return False
        try:
            self._embed_batch(chunk.document_id, [chunk])
        except EmbeddingError:
            return False
        return True

    def export_collection(self, collection_id: str | None = None) -> dict:
        documents = self.repository.list_documents(collection_id)
        nodes, edges = self.repository.graph(collection_id=collection_id, limit=1000)
        return {"format": "iris-knowledge-export", "version": 1, "exported_at": time.time(), "collection_id": collection_id,
                "documents": [{**document.to_dict(), "chunks": [chunk.to_dict() for chunk in self.repository.chunks_for_document(document.id)]} for document in documents],
                "graph": {"nodes": [node.__dict__ if hasattr(node, "__dict__") else {"id": node.id, "label": node.label, "kind": node.kind, "document_count": node.document_count} for node in nodes],
                          "edges": [{"source": edge.source, "target": edge.target, "relation": edge.relation, "document_id": edge.document_id, "confidence": edge.confidence, "evidence_chunk_id": edge.evidence_chunk_id} for edge in edges]}}

    def collection_stats(self, collection_id: str | None = None) -> dict:
        documents = self.repository.list_documents(collection_id)
        nodes, edges = self.repository.graph(collection_id=collection_id, limit=1000)
        return {"documents": len(documents), "ready": sum(item.status == "ready" for item in documents),
                "indexing": sum(item.status in {"queued", "indexing"} for item in documents), "failed": sum(item.status == "failed" for item in documents),
                "chunks": sum(len(self.repository.chunks_for_document(item.id)) for item in documents), "nodes": len(nodes), "edges": len(edges)}

    def import_backup(self, backup: dict, collection_id: str) -> int:
        if not isinstance(backup, dict) or backup.get("format") != "iris-knowledge-export":
            raise ValueError("不是 Iris 知识库备份文件")
        documents = backup.get("documents")
        if not isinstance(documents, list) or len(documents) > 100:
            raise ValueError("备份资料数量无效")
        imported = 0
        for item in documents:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()[:200]
            chunks = item.get("chunks")
            if not title or not isinstance(chunks, list):
                continue
            content = "\n\n".join(str(chunk.get("content") or "").strip() for chunk in chunks if isinstance(chunk, dict)).strip()
            if content:
                self.enqueue_text(title, content, source_type="manual", collection_id=collection_id)
                imported += 1
        return imported

    def evaluate_queries(self, questions: list[str], collection_id: str | None = None, cases: list[dict] | None = None,
                         k_values: list[int] | None = None) -> dict:
        ks = sorted({int(value) for value in (k_values or [1, 3, 5, 10]) if not isinstance(value, bool) and 1 <= int(value) <= 50})
        if not ks:
            raise ValueError("评测 K 值必须包含 1 到 50 之间的整数")
        results = []
        metric_rows = []
        for raw_case in (cases or [{"question": item} for item in questions])[:200]:
            text = str(raw_case.get("question") or "").strip()
            if not text:
                continue
            hits = self.search(text, limit=max(ks), collection_id=collection_id)
            expected_id = str(raw_case.get("expected_document_id") or "").strip()
            expected_title = str(raw_case.get("expected_title") or "").strip().casefold()
            expected_answer = str(raw_case.get("expected_answer") or "").strip()
            relevant_chunks = {str(value).strip() for value in raw_case.get("relevant_chunk_ids", []) if str(value).strip()}
            relevant_documents = {str(value).strip() for value in raw_case.get("relevant_document_ids", []) if str(value).strip()}
            relevant_titles = {str(value).strip().casefold() for value in raw_case.get("relevant_titles", []) if str(value).strip()}
            if expected_id:
                relevant_documents.add(expected_id)
            if expected_title:
                relevant_titles.add(expected_title)
            if relevant_chunks:
                relevant_keys = relevant_chunks
                predicted_keys = [hit.chunk_id for hit in hits]
            elif relevant_documents:
                relevant_keys = relevant_documents
                predicted_keys = [hit.document_id for hit in hits]
            else:
                relevant_keys = relevant_titles
                predicted_keys = [hit.title.strip().casefold() for hit in hits]
            predicted_keys = list(dict.fromkeys(predicted_keys))
            expected_ranks = [index + 1 for index, key in enumerate(predicted_keys) if key in relevant_keys]
            rank = expected_ranks[0] if expected_ranks else None
            status = "pass" if rank else ("hit" if hits else "miss")
            case_metrics = None
            if relevant_keys:
                hit_rate, recall, precision, ndcg = {}, {}, {}, {}
                for k in ks:
                    top = predicted_keys[:k]
                    relevant_count = sum(key in relevant_keys for key in top)
                    hit_rate[str(k)] = float(relevant_count > 0)
                    recall[str(k)] = relevant_count / len(relevant_keys)
                    precision[str(k)] = relevant_count / k
                    dcg = sum(1 / math.log2(index + 2) for index, key in enumerate(top) if key in relevant_keys)
                    ideal_count = min(len(relevant_keys), k)
                    idcg = sum(1 / math.log2(index + 2) for index in range(ideal_count))
                    ndcg[str(k)] = dcg / idcg if idcg else 0.0
                case_metrics = {"hit_rate": hit_rate, "recall": recall, "precision": precision, "ndcg": ndcg,
                                "reciprocal_rank": 1 / rank if rank else 0.0}
                metric_rows.append(case_metrics)
            answer_quality = None
            if expected_answer and hits and self.graph_extractor:
                try:
                    answer_quality = self.graph_extractor.evaluate_retrieval_answer(text, expected_answer, [hit.content for hit in hits])
                except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError):
                    answer_quality = {"answer": "", "answer_score": None, "grounded": None, "reason": "本地答案评测暂不可用"}
            results.append({"question": text, "expected_title": raw_case.get("expected_title") or None,
                            "expected_document_id": expected_id or None,
                            "relevant_document_ids": sorted(relevant_documents), "relevant_chunk_ids": sorted(relevant_chunks),
                            "expected_answer": expected_answer or None, "status": status,
                            "top_score": round(hits[0].score, 4) if hits else 0.0, "expected_rank": rank,
                            "metrics": case_metrics, "answer_quality": answer_quality,
                            "hits": [{"title": hit.title, "document_id": hit.document_id, "chunk_id": hit.chunk_id,
                                      "score": round(hit.score, 4), "excerpt": hit.content[:220], "routes": list(hit.routes)} for hit in hits]})
        judged = [item for item in results if item["metrics"] is not None]
        route_coverage = {route: sum(route in hit["routes"] for item in results for hit in item["hits"]) for route in ("keyword", "vector", "graph", "reranker")}
        answer_scores = [item["answer_quality"]["answer_score"] for item in results if item.get("answer_quality") and item["answer_quality"].get("answer_score") is not None]
        grounded = [item["answer_quality"]["grounded"] for item in results if item.get("answer_quality") and item["answer_quality"].get("grounded") is not None]
        def averages(name: str) -> dict[str, float]:
            return {str(k): round(sum(row[name][str(k)] for row in metric_rows) / len(metric_rows), 3) for k in ks}
        metrics = ({"k_values": ks, "hit_rate": averages("hit_rate"), "recall": averages("recall"),
                    "precision": averages("precision"), "ndcg": averages("ndcg"),
                    "mrr": round(sum(row["reciprocal_rank"] for row in metric_rows) / len(metric_rows), 3)}
                   if metric_rows else {"k_values": ks, "hit_rate": {}, "recall": {}, "precision": {}, "ndcg": {}, "mrr": None})
        recall_at_1 = metrics["hit_rate"].get("1")
        recall_at_3 = metrics["hit_rate"].get("3")
        mrr = metrics["mrr"]
        evaluation = {"collection_id": collection_id, "total": len(results), "hit_count": sum(item["status"] != "miss" for item in results), "judged_total": len(judged),
                "recall_at_1": recall_at_1, "recall_at_3": recall_at_3, "mrr": mrr,
                "hit_at_1": recall_at_1, "hit_at_3": recall_at_3, "metrics": metrics,
                "answer_score": round(sum(answer_scores) / len(answer_scores), 3) if answer_scores else None,
                "grounded_rate": round(sum(bool(value) for value in grounded) / len(grounded), 3) if grounded else None,
                "route_coverage": route_coverage, "recommendations": self._evaluation_recommendations(collection_id, recall_at_1, recall_at_3, mrr), "results": results}
        evaluation["quality_gate"] = self._evaluate_quality_gate(collection_id, recall_at_1, recall_at_3, mrr)
        if collection_id:
            evaluation["history_id"] = self._record_evaluation_history(collection_id, evaluation)
        return evaluation

    def evaluation_gate(self, collection_id: str) -> dict[str, float]:
        self.collection_retrieval_config(collection_id)
        target = self.evaluation_directory / f"gate-{collection_id}.json"
        if not target.exists():
            return {"recall_at_1": 0.7, "recall_at_3": 0.8, "mrr": 0.75}
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("评测门禁文件损坏") from exc
        if not isinstance(payload, dict):
            raise ValueError("评测门禁文件损坏")
        return self._normalise_evaluation_gate(payload)

    def update_evaluation_gate(self, collection_id: str, updates: dict[str, object]) -> dict[str, float]:
        current = self.evaluation_gate(collection_id)
        current.update(updates)
        gate = self._normalise_evaluation_gate(current)
        target = self.evaluation_directory / f"gate-{collection_id}.json"
        target.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
        return gate

    @staticmethod
    def _normalise_evaluation_gate(values: dict[str, object]) -> dict[str, float]:
        keys = ("recall_at_1", "recall_at_3", "mrr")
        try:
            gate = {key: float(values[key]) for key in keys}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("评测门禁必须包含 Recall@1、Recall@3 和 MRR 阈值") from exc
        if any(value < 0 or value > 1 for value in gate.values()):
            raise ValueError("评测门禁阈值应在 0 到 1 之间")
        return gate

    def _evaluate_quality_gate(self, collection_id: str | None, recall_at_1: float | None, recall_at_3: float | None, mrr: float | None) -> dict:
        if not collection_id:
            return {"thresholds": None, "passed": None, "failures": []}
        thresholds = self.evaluation_gate(collection_id)
        metrics = {"recall_at_1": recall_at_1, "recall_at_3": recall_at_3, "mrr": mrr}
        if any(value is None for value in metrics.values()):
            return {"thresholds": thresholds, "passed": None, "failures": []}
        failures = [{"metric": key, "actual": value, "threshold": thresholds[key]} for key, value in metrics.items() if value is not None and value < thresholds[key]]
        return {"thresholds": thresholds, "passed": not failures, "failures": failures}

    def evaluation_history(self, collection_id: str, limit: int = 20) -> dict:
        self.collection_retrieval_config(collection_id)
        if limit < 1:
            raise ValueError("评测历史数量必须大于 0")
        with self._evaluation_lock:
            items = self._load_evaluation_history(collection_id)
        return {"collection_id": collection_id, "items": items[:min(limit, 100)]}

    def restore_evaluation_config(self, collection_id: str, history_id: str) -> dict[str, int | float]:
        if not history_id:
            raise ValueError("评测历史记录不能为空")
        self.collection_retrieval_config(collection_id)
        with self._evaluation_lock:
            item = next((candidate for candidate in self._load_evaluation_history(collection_id) if candidate["id"] == history_id), None)
        if item is None:
            raise ValueError("未找到评测历史记录")
        return self.update_collection_retrieval_config(collection_id, item["config"])

    def _evaluation_history_path(self, collection_id: str) -> Path:
        self.collection_retrieval_config(collection_id)
        return self.evaluation_directory / f"history-{collection_id}.json"

    def _load_evaluation_history(self, collection_id: str) -> list[dict]:
        target = self._evaluation_history_path(collection_id)
        if not target.exists():
            return []
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("评测历史文件损坏") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("config"), dict) for item in items):
            raise ValueError("评测历史文件损坏")
        return items

    def _record_evaluation_history(self, collection_id: str, evaluation: dict) -> str:
        record = {
            "id": f"evaluation-{uuid4().hex[:12]}", "created_at": time.time(),
            "total": evaluation["total"], "hit_count": evaluation["hit_count"], "judged_total": evaluation["judged_total"],
            "recall_at_1": evaluation["recall_at_1"], "recall_at_3": evaluation["recall_at_3"], "mrr": evaluation["mrr"],
            "hit_at_1": evaluation["hit_at_1"], "hit_at_3": evaluation["hit_at_3"], "metrics": evaluation["metrics"],
            "config": self.collection_retrieval_config(collection_id),
        }
        with self._evaluation_lock:
            target = self._evaluation_history_path(collection_id)
            payload = {"version": 1, "collection_id": collection_id, "items": [record, *self._load_evaluation_history(collection_id)][:20]}
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)
        return record["id"]

    def _evaluation_recommendations(
        self, collection_id: str | None, recall_at_1: float | None, recall_at_3: float | None, mrr: float | None
    ) -> list[dict[str, object]]:
        if collection_id is None or recall_at_3 is None:
            return []
        config = self.collection_retrieval_config(collection_id)
        if recall_at_3 < 0.7 and int(config["candidate_multiplier"]) < 10:
            return [{
                "field": "candidate_multiplier", "current": config["candidate_multiplier"],
                "suggested": int(config["candidate_multiplier"]) + 1,
                "reason": "Hit@3 偏低，扩大候选集以减少漏召回。",
            }]
        if recall_at_1 is not None and mrr is not None and recall_at_1 < 0.7 and mrr < 0.8 and float(config["mmr_relevance_weight"]) < 1:
            return [{
                "field": "mmr_relevance_weight", "current": config["mmr_relevance_weight"],
                "suggested": round(min(1.0, float(config["mmr_relevance_weight"]) + 0.1), 2),
                "reason": "召回已覆盖但首位排序偏弱，提高相关性权重以优先最匹配切片。",
            }]
        return []

    def save_evaluation_cases(self, cases: list[dict], collection_id: str | None = None) -> dict:
        normalised = [dict(item) for item in cases if isinstance(item, dict) and str(item.get("question") or "").strip()]
        if not normalised:
            raise ValueError("评测集必须包含 question")
        target = self.evaluation_directory / f"seed-{collection_id or 'all'}.json"
        payload = {"version": 1, "updated_at": time.time(), "collection_id": collection_id, "cases": normalised[:200]}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"version": 1, "collection_id": collection_id, "count": len(payload["cases"]), "path": str(target)}

    def load_evaluation_cases(self, collection_id: str | None = None) -> dict:
        target = self.evaluation_directory / f"seed-{collection_id or 'all'}.json"
        if not target.exists():
            return {"version": 1, "collection_id": collection_id, "cases": []}
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("评测集文件损坏") from exc
        return payload if isinstance(payload, dict) else {"version": 1, "collection_id": collection_id, "cases": []}

    def validate_evaluation_cases(self, cases: list[dict], collection_id: str | None = None) -> dict:
        valid_chunk_ids = {
            chunk.id
            for document in self.repository.list_documents(collection_id)
            for chunk in self.repository.chunks_for_document(document.id)
        }
        questions = [str(case.get("question") or "").strip().casefold() for case in cases]
        duplicate_questions = {question for question in questions if question and questions.count(question) > 1}
        rows = []
        for index, case in enumerate(cases):
            relevant_chunks = [str(value).strip() for value in case.get("relevant_chunk_ids", []) if str(value).strip()]
            annotated = bool(
                relevant_chunks
                or case.get("relevant_document_ids")
                or str(case.get("expected_document_id") or "").strip()
                or str(case.get("expected_title") or "").strip()
                or case.get("relevant_titles")
            )
            rows.append({
                "index": index,
                "duplicate": questions[index] in duplicate_questions,
                "empty_annotation": not annotated,
                "invalid_chunk_ids": [chunk_id for chunk_id in relevant_chunks if chunk_id not in valid_chunk_ids],
            })
        return {
            "summary": {
                "total": len(rows),
                "annotated": sum(not row["empty_annotation"] for row in rows),
                "duplicates": sum(row["duplicate"] for row in rows),
                "empty_annotations": sum(row["empty_annotation"] for row in rows),
                "invalid_chunks": sum(len(row["invalid_chunk_ids"]) for row in rows),
            },
            "rows": rows,
        }

    def record_bad_case(self, case: dict) -> dict:
        question = str(case.get("question") or "").strip()
        if not question:
            raise ValueError("bad case 必须包含 question")
        item = {"id": f"bad-{uuid4().hex[:12]}", "created_at": time.time(), "question": question,
                "collection_id": case.get("collection_id"), "expected_title": case.get("expected_title"),
                "relevant_chunk_ids": list(case.get("relevant_chunk_ids") or []),
                "relevant_document_ids": list(case.get("relevant_document_ids") or []),
                "expected_answer": case.get("expected_answer") or "", "actual_answer": case.get("actual_answer") or "",
                "reason": case.get("reason") or ""}
        with (self.evaluation_directory / "bad-cases.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def list_bad_cases(self, limit: int = 100) -> list[dict]:
        target = self.evaluation_directory / "bad-cases.jsonl"
        if not target.exists():
            return []
        rows = []
        for line in target.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 500)):]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return list(reversed(rows))

    def replay_bad_case(self, case_id: str) -> dict:
        case = next((item for item in self.list_bad_cases(500) if item.get("id") == case_id), None)
        if case is None:
            raise ValueError("bad case 不存在")
        return {"case": case, "evaluation": self.evaluate_queries([], case.get("collection_id"), [case])}

    def generate_evaluation_cases(self, collection_id: str | None = None) -> dict:
        documents = [item for item in self.repository.list_documents(collection_id) if item.status == "ready"][:8]
        sources = []
        for document in documents:
            content = "\n".join(chunk.content for chunk in self.repository.chunks_for_document(document.id)[:2]).strip()[:2400]
            if content: sources.append({"title": document.title, "content": content})
        if not sources: return {"cases": [], "generated_by": "none"}
        try:
            cases = self.graph_extractor.evaluation_cases(sources) if self.graph_extractor else []
            if cases: return {"cases": cases, "generated_by": "ollama"}
        except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError):
            pass
        return {"cases": [{"question": f"请概述《{item['title']}》的核心内容。", "expected_title": item["title"], "expected_answer": ""} for item in sources], "generated_by": "fallback"}

    def duplicate_suggestions(self, collection_id: str | None = None) -> list[dict]:
        documents = self.repository.list_documents(collection_id)
        suggestions: list[dict] = []
        for index, left in enumerate(documents):
            left_text = " ".join(chunk.content for chunk in self.repository.chunks_for_document(left.id))[:3000]
            for right in documents[index + 1:]:
                title_score = SequenceMatcher(None, left.title.casefold(), right.title.casefold()).ratio()
                same_file = bool(left.original_name and right.original_name and left.original_name.casefold() == right.original_name.casefold())
                right_text = " ".join(chunk.content for chunk in self.repository.chunks_for_document(right.id))[:3000]
                content_score = SequenceMatcher(None, left_text, right_text).ratio() if left_text and right_text else 0.0
                score = max(content_score, title_score if same_file else 0.0, 1.0 if same_file else 0.0)
                if score >= 0.84:
                    suggestions.append({"left": {"id": left.id, "title": left.title}, "right": {"id": right.id, "title": right.title}, "score": round(score, 3), "reason": "原文件名相同" if same_file else ("正文高度相似" if content_score >= title_score else "标题高度相似")})
        return sorted(suggestions, key=lambda item: -item["score"])[:30]

    def merge_graph_entities(self, collection_id: str | None = None) -> int:
        labels = self.repository.graph_entity_labels(collection_id)
        aliases = {label: canonical_graph_label(label) for label in labels if canonical_graph_label(label) != label}
        if self.graph_extractor is not None:
            try:
                aliases.update(self.graph_extractor.aliases(labels))
            except (httpx.HTTPError, OSError, ValueError):
                pass
        return self.repository.merge_graph_entities(aliases)

    def summarize_graph_entity(self, node_id: str, collection_id: str | None = None) -> dict:
        facts = self.repository.graph_entity_evidence(node_id, collection_id)
        if not facts:
            raise ValueError("图谱实体不存在或没有来源证据")
        label = self.repository.graph_node_label(node_id)
        if not label:
            raise ValueError("图谱实体不存在")
        evidence = [f"{item['source']} —{item['relation']}→ {item['target']}。{str(item.get('evidence') or '')}" for item in facts]
        return self._graph_summary(label, "实体", evidence, facts)

    def summarize_graph_relation(self, source_id: str, target_id: str, relation: str, document_id: str | None = None, collection_id: str | None = None) -> dict:
        facts = self.repository.graph_relation_evidence(source_id, target_id, relation, document_id, collection_id)
        if not facts:
            raise ValueError("图谱关系不存在或没有来源证据")
        label = f"{facts[0]['source']} —{facts[0]['relation']}→ {facts[0]['target']}"
        evidence = [str(item.get("evidence") or "") for item in facts]
        return self._graph_summary(label, "关系", evidence, facts)

    def _graph_summary(self, label: str, kind: str, evidence: list[str], facts: list[dict]) -> dict:
        fallback = next((item.strip().replace("\n", " ")[:180] for item in evidence if item.strip()), "暂无足够来源证据")
        try:
            summary = self.graph_extractor.summarize_graph_item(label, evidence, kind=kind) if self.graph_extractor else fallback
        except (httpx.HTTPError, OSError, ValueError):
            summary = fallback
        return {"label": label, "summary": summary, "evidence_count": len(facts), "facts": [{"source": item["source"], "target": item["target"], "relation": item["relation"], "confidence": round(float(item["confidence"]), 2)} for item in facts]}

    def graph_audit(self, collection_id: str | None = None) -> dict: return self.repository.graph_audit(collection_id)
    def update_graph_relation(self, source_id: str, target_id: str, relation: str, new_relation: str, document_id: str | None = None) -> int:
        return self.repository.update_graph_edge_relation(source_id, target_id, relation, canonical_graph_relation(new_relation), document_id)
    def delete_graph_relation(self, source_id: str, target_id: str, relation: str, document_id: str | None = None) -> int:
        return self.repository.delete_graph_edge(source_id, target_id, relation, document_id)
    def rename_graph_entity(self, node_id: str, label: str, collection_id: str) -> int:
        return self.repository.rename_graph_entity(node_id, canonical_graph_label(label), collection_id)
    def delete_graph_entity(self, node_id: str, collection_id: str) -> int:
        return self.repository.delete_graph_entity(node_id, collection_id)

    def reindex_document(self, document_id: str, *, vectors_only: bool = False) -> KnowledgeDocument:
        document = self.repository.update_document_status(document_id, "queued")
        self._set_index_progress(document_id, "queued", "等待重新建立索引")
        self._indexer.submit(self._index_document, document_id, vectors_only)
        return document

    def reindex_all(self, collection_id: str | None = None) -> int:
        documents = self.repository.list_documents(collection_id)
        for document in documents:
            self.repository.update_document_status(document.id, "queued")
            self._set_index_progress(document.id, "queued", "等待重新建立索引")
            self._indexer.submit(self._index_document, document.id)
        return len(documents)

    def rechunk_document(self, document_id: str) -> KnowledgeDocument:
        """Rebuild chunks from the source text with current chunking settings; reindex afterwards."""
        with self._ingest_lock:
            document = self.repository.get_document(document_id)
            if document is None:
                raise ValueError("知识资料不存在")
            if document.source_type == "upload":
                matches = list(self.files_directory.glob(f"{document_id}.*"))
                if not matches:
                    raise ValueError("导入源文件不存在")
                text, _location, chunks = self._parse_source_file_content(matches[0])
            else:
                text = "\n\n".join(chunk.content for chunk in self.repository.chunks_for_document(document_id))
                chunks = self._build_chunks(text, None, title=document.title)
            if not text.strip():
                raise ValueError("文档没有可重新切片的内容")
            self.repository.replace_document_chunks(document_id, chunks)
            self.repository.update_document_status(document_id, "queued")
        self._indexer.submit(self._index_document, document_id)
        return self.repository.get_document(document_id) or document

    def delete_document(self, document_id: str) -> bool:
        document = self.repository.delete_document(document_id)
        if document is None:
            return False
        for source_file in self.files_directory.glob(f"{document_id}.*"):
            try:
                source_file.unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def move_document(self, document_id: str, collection_id: str) -> KnowledgeDocument:
        return self.repository.move_document(document_id, collection_id)

    def update_text_document(self, document_id: str, title: str, content: str) -> KnowledgeDocument:
        with self._ingest_lock:
            document = self.repository.get_document(document_id)
            if document is None:
                raise ValueError("知识资料不存在")
            if document.source_type == "upload":
                raise ValueError("上传文件请通过重新导入来替换")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("资料正文不能为空")
            size_bytes = len(content.encode("utf-8"))
            self._check_ingest_capacity(size_bytes, replacing_document_id=document_id)
            chunks = self._build_chunks(content, None, title=title)
            updated = self.repository.update_document_text(document_id, title, chunks, size_bytes=size_bytes)
        self._indexer.submit(self._index_document, document_id)
        return updated

    def graph(self, topic: str | None = None, collection_id: str | None = None) -> dict:
        for document in self.repository.list_documents(collection_id):
            if self.repository.graph_edge_count(document.id):
                continue
            chunks = self.repository.chunks_for_document(document.id)
            if chunks:
                entities, relations = self._extract_document_graph(document.title, chunks)
                self.repository.replace_document_graph(document.id, entities, relations)
        self.repository.prune_orphan_graph_nodes()
        nodes, edges = self.repository.graph(topic, collection_id=collection_id)
        return {"nodes": [{"id": node.id, "label": node.label, "kind": node.kind, "document_count": node.document_count} for node in nodes],
                "edges": [{"source": edge.source, "target": edge.target, "relation": edge.relation, "document_id": edge.document_id,
                           "confidence": round(edge.confidence, 2), "evidence": edge.evidence, "evidence_chunk_id": edge.evidence_chunk_id} for edge in edges]}

    def topics(self, collection_id: str | None = None) -> list[str]:
        return [node.label for node in self.repository.graph(limit=100, collection_id=collection_id)[0] if node.kind == "topic"]

    def add_text(self, title: str, content: str, *, source_type: str = "manual", original_name: str | None = None, collection_id: str = "collection-general") -> KnowledgeDocument:
        if not isinstance(content, str) or not content.strip(): raise ValueError("知识内容不能为空")
        size_bytes = len(content.encode("utf-8"))
        with self._ingest_lock:
            self._check_ingest_capacity(size_bytes)
            return self._store(title, content, source_type, "text/plain", size_bytes, original_name, collection_id=collection_id)

    def enqueue_text(self, title: str, content: str, *, source_type: str = "manual", original_name: str | None = None, collection_id: str = "collection-general") -> KnowledgeDocument:
        if not isinstance(content, str) or not content.strip(): raise ValueError("知识内容不能为空")
        size_bytes = len(content.encode("utf-8"))
        with self._ingest_lock:
            self._check_ingest_capacity(size_bytes)
            document = KnowledgeDocument.new(title=title, source_type=source_type, media_type="text/plain", size_bytes=size_bytes, original_name=original_name, status="queued")
            drafts = self._build_chunks(content, None, title=title)
            self.repository.save_document_with_chunks(document, drafts, collection_id=collection_id)
            self._set_index_progress(document.id, "queued", "等待建立索引")
        self._indexer.submit(self._index_document, document.id)
        return document

    def add_upload(self, title: str, original_name: str, content: bytes, media_type: str | None = None, *, collection_id: str = "collection-general") -> KnowledgeDocument:
        suffix = Path(original_name).suffix.lower()
        if suffix not in self.allowed_extensions: raise ValueError("不支持该知识库文件类型")
        if not content or len(content) > self.max_file_bytes: raise ValueError("知识库文件超过大小限制")
        with self._ingest_lock:
            self._check_ingest_capacity(len(content))
            target = self.files_directory / f"{uuid4().hex}{suffix}"
            target.write_bytes(content)
            try:
                text, location, chunks = self._parse_source_file_content(target, title=title or original_name)
                document = self._store(
                    title or original_name, text, "upload", media_type, len(content), original_name,
                    location, collection_id, chunks=chunks,
                )
                target.replace(self.files_directory / f"{document.id}{suffix}")
                return document
            except Exception:
                target.unlink(missing_ok=True)
                raise

    def enqueue_upload(self, title: str, original_name: str, content: bytes, media_type: str | None = None, *, collection_id: str = "collection-general") -> KnowledgeDocument:
        suffix = Path(original_name).suffix.lower()
        if suffix not in self.allowed_extensions: raise ValueError("不支持该知识库文件类型")
        if not content or len(content) > self.max_file_bytes: raise ValueError("知识库文件超过大小限制")
        with self._ingest_lock:
            self._check_ingest_capacity(len(content))
            document = KnowledgeDocument.new(title=title or original_name, source_type="upload", media_type=media_type, size_bytes=len(content), original_name=original_name, status="queued")
            target = self.files_directory / f"{document.id}{suffix}"
            target.write_bytes(content)
            try:
                self.repository.save_document_with_chunks(document, [], collection_id=collection_id)
                self._set_index_progress(document.id, "queued", "等待解析文件")
            except Exception:
                target.unlink(missing_ok=True); raise
        self._indexer.submit(self._index_document, document.id)
        return document

    def search(self, query: str, limit: int | None = None, collection_id: str | None = None) -> list[RagSearchHit]:
        if collection_id is not None:
            return self._search_in_collection(query, limit, collection_id)
        return self._search_across_collections(query, limit)

    def _search_across_collections(self, query: str, limit: int | None) -> list[RagSearchHit]:
        collections = self._route_collections(query)
        if not collections:
            return self._search_in_collection(query, limit, None)
        hits = [
            replace(hit, collection_id=collection.id, collection_name=collection.name)
            for collection in collections
            for hit in self._search_in_collection(query, limit, collection.id)
        ]
        amount = limit or max(int(self.collection_retrieval_config(collection.id)["top_k"]) for collection in collections)
        records = {hit.chunk_id: hit for hit in hits}
        scores = {chunk_id: hit.score for chunk_id, hit in records.items()}
        ordered = sorted(records, key=lambda chunk_id: -scores[chunk_id])
        selected = self._diversify_hits(ordered, records, scores, amount)
        return [records[chunk_id] for chunk_id in selected]

    def _route_collections(self, query: str):
        collections = self.repository.list_collections()
        query_tokens = self._content_tokens(query)
        matched = [
            collection for collection in collections
            if query_tokens & self._content_tokens(f"{collection.name} {collection.description or ''}")
        ]
        return matched or collections

    def _search_in_collection(self, query: str, limit: int | None, collection_id: str | None) -> list[RagSearchHit]:
        hits, _ = self._run_search_pipeline(query, limit, collection_id)
        return hits

    def debug_search(self, query: str, limit: int | None = None, collection_id: str | None = None) -> dict:
        hits, trace = self._run_search_pipeline(query, limit, collection_id)
        return {**trace, "hits": [hit.to_dict() for hit in hits]}

    def _run_search_pipeline(self, query: str, limit: int | None, collection_id: str | None) -> tuple[list[RagSearchHit], dict]:
        pipeline_started = time.perf_counter()
        if not isinstance(query, str) or not query.strip():
            return [], {"query": "", "retrieval_query": "", "collection_id": collection_id, "candidate_limit": 0, "elapsed_ms": 0, "config": {}, "stages": [], "hits": []}
        retrieval_query = expand_retrieval_query(query.strip())
        config = self.collection_retrieval_config(collection_id) if collection_id else self._default_retrieval_config()
        amount = limit or int(config["top_k"])
        candidate_limit = amount * int(config["candidate_multiplier"])
        stage_started = time.perf_counter()
        keyword = self.repository.keyword_search(retrieval_query, candidate_limit, collection_id)
        keyword_elapsed = round((time.perf_counter() - stage_started) * 1000)
        scores: dict[str, float] = {}; records: dict[str, RagSearchHit] = {}
        keyword_scores: dict[str, float] = {}; vector_scores: dict[str, float] = {}; graph_scores: dict[str, float] = {}; reranker_scores: dict[str, float] = {}
        keyword_ids: list[str] = []; graph_ids: list[str] = []; vector_ids: list[str] = []
        for rank, hit in enumerate(keyword, 1):
            contribution = 1.0 / (self.rrf_k + rank)
            keyword_scores[hit.chunk_id] = contribution
            keyword_ids.append(hit.chunk_id)
            self._add_hit(records, scores, hit.chunk_id, hit.document_id, hit.title, hit.content, hit.location, contribution)
        stage_started = time.perf_counter()
        try:
            for rank, hit in enumerate(self.repository.graph_search(retrieval_query, candidate_limit, collection_id), 1):
                contribution = 0.8 / (self.rrf_k + rank)
                graph_scores[hit.chunk_id] = contribution
                graph_ids.append(hit.chunk_id)
                self._add_hit(records, scores, hit.chunk_id, hit.document_id, hit.title, hit.content, hit.location, contribution)
        except (OSError, ValueError):
            pass
        graph_elapsed = round((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
        if self.embedder is not None:
            try:
                vector = self.embedder.embed([retrieval_query])[0]
                for rank, (similarity, candidate) in enumerate(self._vector_candidates(vector, candidate_limit, collection_id), 1):
                    if similarity > 0:
                        contribution = 1.0 / (self.rrf_k + rank)
                        vector_scores[candidate.chunk_id] = contribution
                        vector_ids.append(candidate.chunk_id)
                        self._add_hit(records, scores, candidate.chunk_id, candidate.document_id, candidate.title, candidate.content, candidate.location, contribution)
            except (EmbeddingError, OSError, ValueError):
                pass
        vector_elapsed = round((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
        ordered_ids = sorted(records, key=lambda item: -scores[item])
        fused_ids = list(ordered_ids)
        fused_scores = dict(scores)
        fused_elapsed = round((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
        if self.reranker is not None and ordered_ids:
            finalists = ordered_ids[:self.reranker_candidates]
            try:
                relevance = self.reranker.score(query, [(chunk_id, records[chunk_id].content) for chunk_id in finalists])
                if relevance:
                    baseline = {chunk_id: 1.0 - index / max(len(finalists), 1) for index, chunk_id in enumerate(finalists)}
                    for chunk_id, score in relevance.items():
                        if chunk_id not in baseline:
                            continue
                        reranker_scores[chunk_id] = score
                        scores[chunk_id] = 0.75 * score + 0.25 * baseline[chunk_id]
                    ordered_ids = sorted(reranker_scores, key=lambda item: -scores[item])
            except (httpx.HTTPError, OSError, ValueError):
                pass
        reranker_elapsed = round((time.perf_counter() - stage_started) * 1000)
        reranked_ids = list(ordered_ids)
        reranked_scores = dict(scores)
        stage_started = time.perf_counter()
        rrf_ceiling = 2.8 / (self.rrf_k + 1)
        final_scores = {
            key: min(1.0, scores[key]) if key in reranker_scores else min(1.0, scores[key] / rrf_ceiling)
            for key in ordered_ids
        }
        ordered_ids = sorted(ordered_ids, key=lambda item: -final_scores[item])
        ordered_ids = self._diversify_hits(ordered_ids, records, final_scores, amount, float(config["mmr_relevance_weight"]))
        final_ids = ordered_ids[:amount]
        final_elapsed = round((time.perf_counter() - stage_started) * 1000)
        hits = [RagSearchHit(records[key].document_id, records[key].chunk_id, records[key].title,
                             records[key].content, records[key].location, final_scores[key], keyword_scores.get(key, 0.0),
                             vector_scores.get(key, 0.0), reranker_scores.get(key), graph_scores.get(key, 0.0),
                             tuple(route for route, value in (("keyword", keyword_scores.get(key)), ("vector", vector_scores.get(key)), ("graph", graph_scores.get(key)), ("reranker", reranker_scores.get(key))) if value is not None and value > 0))
                for key in final_ids]

        def candidates(ids: list[str], stage_scores: dict[str, float]) -> list[dict]:
            return [{
                "rank": rank, "document_id": records[key].document_id, "chunk_id": key,
                "title": records[key].title, "content": records[key].content[:500], "location": records[key].location,
                "score": round(float(stage_scores.get(key, 0.0)), 4),
                "keyword_score": round(keyword_scores.get(key, 0.0), 4),
                "vector_score": round(vector_scores.get(key, 0.0), 4),
                "graph_score": round(graph_scores.get(key, 0.0), 4),
                "reranker_score": None if key not in reranker_scores else round(reranker_scores[key], 4),
                "routes": [route for route, value in (("keyword", keyword_scores.get(key)), ("vector", vector_scores.get(key)), ("graph", graph_scores.get(key)), ("reranker", reranker_scores.get(key))) if value is not None and value > 0],
            } for rank, key in enumerate(ids, 1)]

        stages = [
            {"key": "keyword", "label": "关键词召回", "enabled": True, "elapsed_ms": keyword_elapsed, "candidates": candidates(keyword_ids, keyword_scores)},
            {"key": "graph", "label": "图谱召回", "enabled": True, "elapsed_ms": graph_elapsed, "candidates": candidates(graph_ids, graph_scores)},
            {"key": "vector", "label": "向量召回", "enabled": self.embedder is not None, "elapsed_ms": vector_elapsed, "candidates": candidates(vector_ids, vector_scores)},
            {"key": "fused", "label": "RRF 融合", "enabled": True, "elapsed_ms": fused_elapsed, "candidates": candidates(fused_ids, fused_scores)},
            {"key": "reranked", "label": "模型重排", "enabled": self.reranker is not None, "elapsed_ms": reranker_elapsed, "candidates": candidates(reranked_ids, reranked_scores)},
            {"key": "final", "label": "MMR 最终结果", "enabled": True, "elapsed_ms": final_elapsed, "candidates": candidates(final_ids, final_scores)},
        ]
        trace = {"query": query.strip(), "retrieval_query": retrieval_query, "collection_id": collection_id, "candidate_limit": candidate_limit,
                 "elapsed_ms": round((time.perf_counter() - pipeline_started) * 1000), "config": config, "stages": stages}
        return hits, trace

    @staticmethod
    def _content_tokens(content: str) -> set[str]:
        tokens: set[str] = set()
        for segment in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", content.casefold()):
            if "\u4e00" <= segment[0] <= "\u9fff":
                tokens.update(segment[index:index + 2] for index in range(max(1, len(segment) - 1)))
            else:
                tokens.add(segment)
        return tokens

    def _diversify_hits(self, ordered_ids: list[str], records: dict[str, RagSearchHit], scores: dict[str, float], limit: int,
                        relevance_weight: float | None = None) -> list[str]:
        if limit <= 0 or not ordered_ids:
            return []
        relevance_weight = self._mmr_relevance_weight if relevance_weight is None else relevance_weight
        token_sets = {chunk_id: self._content_tokens(records[chunk_id].content) for chunk_id in ordered_ids}
        selected: list[str] = []
        remaining = list(ordered_ids)
        while remaining and len(selected) < limit:
            selected_tokens = [token_sets[chunk_id] for chunk_id in selected]
            best_id = max(
                remaining,
                key=lambda chunk_id: (
                    relevance_weight * scores[chunk_id]
                    - (1 - relevance_weight) * max(
                        (
                            len(token_sets[chunk_id] & chosen_tokens) / len(token_sets[chunk_id] | chosen_tokens)
                            for chosen_tokens in selected_tokens
                            if token_sets[chunk_id] or chosen_tokens
                        ),
                        default=0.0,
                    )
                ),
            )
            selected.append(best_id)
            remaining.remove(best_id)
        return selected

    def _vector_candidates(self, vector: list[float], candidate_limit: int, collection_id: str | None) -> list[tuple[float, object]]:
        """Prefer the sqlite-vec ANN index; fall back to a full cosine scan."""
        try:
            if hasattr(self.repository, "embedding_search"):
                return [(hit.similarity, hit) for hit in self.repository.embedding_search(vector, candidate_limit, collection_id)]
        except (SqliteKnowledgeRepositoryError, ValueError, OSError):
            pass
        ranked = sorted(((self._cosine(vector, candidate.vector), candidate) for candidate in self.repository.embedding_candidates(collection_id=collection_id)), key=lambda pair: -pair[0])
        return ranked[:candidate_limit]

    def context_for(self, query: str, collection_id: str | None = None, mode: str = "mix") -> tuple[str, list[dict]]:
        if mode not in {"precise", "global", "mix"}:
            mode = "mix"
        minimum_relevance_score = self.minimum_relevance_score if collection_id is None else float(
            self.collection_retrieval_config(collection_id)["minimum_relevance_score"]
        )
        hits = [] if mode == "global" else [
            hit for hit in self.search(query, collection_id=collection_id)
            if hit.score >= (
                minimum_relevance_score if collection_id else float(self.collection_retrieval_config(hit.collection_id or "collection-general")["minimum_relevance_score"])
            )
        ]
        parent_map: dict = {}
        if hits and hasattr(self.repository, "parent_context_for"):
            try:
                parent_map = self.repository.parent_context_for([hit.chunk_id for hit in hits])
            except (SqliteKnowledgeRepositoryError, ValueError, OSError):
                parent_map = {}
        parts: list[str] = []; citations: list[dict] = []; used = 0; index = 0
        seen_parents: set[str] = set()
        for hit in hits:
            parent = parent_map.get(hit.chunk_id)
            if parent is not None:
                if parent.id in seen_parents:
                    continue
                seen_parents.add(parent.id)
            index += 1
            text = (parent.content if parent is not None else hit.content).strip()
            remaining = self.max_context_chars - used
            if remaining <= 0: break
            text = text[:remaining]
            collection_label = f" · {hit.collection_name}" if hit.collection_name else ""
            parts.append(f"[{index}] 《{hit.title}》{collection_label}{('（' + hit.location + '）') if hit.location else ''}\n{text}")
            citations.append({"index": index, **hit.to_dict()}); used += len(text)
        graph_document_ids = list(dict.fromkeys(hit.document_id for hit in hits))
        graph_context = self.repository.global_graph_context(query, collection_id) if mode == "global" else (self.repository.graph_context(graph_document_ids, collection_id) if mode != "precise" else [])
        relation_lines = []
        for relation in graph_context:
            evidence = str(relation.get("evidence") or "").strip().replace("\n", " ")[:180]
            index = len(citations) + 1
            line = f"[{index}] {relation['source']} —{relation['relation']}→ {relation['target']}" + (f"（证据：{evidence}）" if evidence else "")
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break
            line = line[:remaining]
            relation_lines.append(line)
            used += len(line)
            citations.append({
                "index": index,
                "document_id": relation["document_id"],
                "chunk_id": relation.get("evidence_chunk_id") or "",
                "title": relation["title"],
                "content": evidence or f"{relation['source']} —{relation['relation']}→ {relation['target']}",
                "location": None,
                "score": round(float(relation.get("confidence") or 0.0), 4),
                "keyword_score": 0.0,
                "vector_score": 0.0,
                "reranker_score": None,
                "graph_score": round(float(relation.get("confidence") or 0.0), 4),
                "routes": ["graph"],
            })
        graph_section = "\n\n[资料中的知识图谱关系]\n" + "\n".join(relation_lines) if relation_lines else ""
        if not parts and not graph_section:
            return "", []
        heading = {"precise": "[本地知识库精准检索结果]", "global": "[本地知识库全局图谱关系]", "mix": "[本地知识库综合检索结果]"}[mode]
        return heading + "\n" + "\n\n".join(parts) + graph_section + "\n回答涉及上述内容时请用 [1]、[2] 标明来源。", citations

    def _store(self, title: str, content: str, source_type: str, media_type: str | None, size_bytes: int, original_name: str | None, location: str | None = None, collection_id: str = "collection-general", chunks: list | None = None) -> KnowledgeDocument:
        document = KnowledgeDocument.new(title=title, source_type=source_type, media_type=media_type,
                                         size_bytes=size_bytes, original_name=original_name, status="indexing")
        drafts = chunks if chunks is not None else self._build_chunks(content, location, title=title)
        self.repository.save_document_with_chunks(document, drafts, collection_id=collection_id)
        chunks = self.repository.chunks_for_document(document.id)
        self._set_index_progress(document.id, "graph", "正在提取知识图谱")
        entities, relations = self._extract_document_graph(title, chunks)
        self.repository.replace_document_graph(document.id, entities, relations)
        self.repository.replace_document_mindmap(document.id, self._extract_document_mindmap(title, chunks))
        if self.embedder is not None and drafts:
            try:
                self._set_index_progress(document.id, "embedding", "正在生成向量索引")
                self._embed_chunks(document.id, chunks)
            except (EmbeddingError, OSError, ValueError) as exc:
                self._set_index_progress(document.id, "failed", str(exc), failed_stage="embedding")
                return self.repository.update_document_status(document.id, "failed", str(exc)[:500])
        self._set_index_progress(document.id, "completed", "索引已完成")
        return self.repository.update_document_status(document.id, "ready")

    def _index_document(self, document_id: str, vectors_only: bool = False) -> None:
        current_stage = "queued"
        try:
            document = self.repository.update_document_status(document_id, "indexing")
            chunks = self.repository.chunks_for_document(document_id)
            if not chunks and document.source_type == "upload":
                current_stage = "parsing"
                self._set_index_progress(document_id, current_stage, "正在解析文件内容")
                matches = list(self.files_directory.glob(f"{document_id}.*"))
                if not matches: raise ValueError("导入源文件不存在")
                _text, _location, drafts = self._parse_source_file_content(matches[0], title=document.title)
                current_stage = "chunking"
                self._set_index_progress(document_id, current_stage, "正在生成父子切片")
                chunks = self.repository.replace_document_chunks(document_id, drafts)
            if not vectors_only:
                current_stage = "graph"
                self._set_index_progress(document_id, current_stage, "正在提取知识图谱与思维导图")
                entities, relations = self._extract_document_graph(document.title, chunks)
                self.repository.replace_document_graph(document_id, entities, relations)
                self.repository.replace_document_mindmap(document_id, self._extract_document_mindmap(document.title, chunks))
            if self.embedder is not None and chunks:
                current_stage = "embedding"
                self._set_index_progress(document_id, current_stage, "正在生成向量索引")
                self._embed_chunks(document_id, chunks)
            self.repository.update_document_status(document_id, "ready")
            self._set_index_progress(document_id, "completed", "索引已完成")
        except Exception as exc:
            self._set_index_progress(document_id, "failed", str(exc), failed_stage=current_stage)
            try: self.repository.update_document_status(document_id, "failed", str(exc)[:500])
            except Exception: pass

    def _check_ingest_capacity(self, size_bytes: int, *, replacing_document_id: str | None = None) -> None:
        documents = self.repository.list_documents()
        if replacing_document_id is None and len(documents) >= self.max_document_count:
            raise ValueError("知识库文档数量已达上限")
        current_size = sum(item.size_bytes for item in documents if item.id != replacing_document_id)
        if current_size + size_bytes > self.max_total_bytes:
            raise ValueError("知识库文件总大小已达上限")

    def _embed_chunks(self, document_id: str, chunks) -> None:
        if self.embedder is None:
            return
        parent_ids = {chunk.parent_id for chunk in chunks if chunk.parent_id is not None}
        retrieval_chunks = [chunk for chunk in chunks if chunk.id not in parent_ids]
        for start in range(0, len(retrieval_chunks), self.embedding_batch_size):
            batch = retrieval_chunks[start:start + self.embedding_batch_size]
            self._embed_batch(document_id, batch)

    def _embed_batch(self, document_id: str, batch) -> None:
        try:
            vectors = self.embedder.embed([item.content for item in batch])
        except EmbeddingError:
            if len(batch) == 1:
                vector = self._embed_text_resilient(batch[0].content)
                self.repository.save_embeddings(
                    document_id,
                    self.embedder.model,
                    {batch[0].id: vector},
                )
                return
            middle = len(batch) // 2
            self._embed_batch(document_id, batch[:middle])
            self._embed_batch(document_id, batch[middle:])
            return
        self.repository.save_embeddings(
            document_id,
            self.embedder.model,
            zip((item.id for item in batch), vectors),
        )

    def _embed_text_resilient(self, text: str) -> list[float]:
        try:
            return self.embedder.embed([text])[0]
        except EmbeddingError:
            if len(text) <= 1:
                raise
            middle = len(text) // 2
            left_text, right_text = text[:middle], text[middle:]
            left = self._embed_text_resilient(left_text)
            right = self._embed_text_resilient(right_text)
            if len(left) != len(right):
                raise EmbeddingError("embedding 子段向量维度不一致")
            total = len(left_text) + len(right_text)
            return [
                (left_value * len(left_text) + right_value * len(right_text)) / total
                for left_value, right_value in zip(left, right)
            ]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right): return 0.0
        denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0

    @staticmethod
    def _add_hit(records, scores, chunk_id, document_id, title, content, location, score):
        records.setdefault(chunk_id, RagSearchHit(document_id, chunk_id, title, content, location, 0.0)); scores[chunk_id] = scores.get(chunk_id, 0.0) + score

    def _extract_document_mindmap(self, title: str, chunks):
        if self.graph_extractor is not None and hasattr(self.graph_extractor, "mind_map"):
            try:
                nodes = self.graph_extractor.mind_map(title, chunks)
                if len(nodes) > 1:
                    return nodes
            except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError):
                pass
        return build_fallback_mindmap(title, chunks)

    def _extract_document_graph(self, title: str, chunks) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, str | None, float]]]:
        """Extract each stored chunk so long documents have graph coverage and evidence."""
        topic = canonical_graph_label(title)[:120]
        entity_kinds: dict[str, str] = {topic: "topic"}
        relations: list[tuple[str, str, str, str | None, float]] = []
        seen: set[tuple[str, str, str, str | None]] = set()
        has_outline = False
        if self.graph_extractor and chunks:
            try:
                core_entities, core_relations = self.graph_extractor.outline(title, "\n\n".join(chunk.content for chunk in chunks))
                has_outline = bool(core_entities)
                for label, kind in core_entities:
                    entity_kinds[label] = kind
                    relations.append((topic, label, "核心概念", None, 0.9))
                for source, target, relation in core_relations:
                    relations.append((source, target, relation, None, 0.9))
            except (httpx.HTTPError, OSError, ValueError):
                pass
        for chunk in chunks:
            try:
                extracted_entities, extracted_relations = self.graph_extractor.extract(title, chunk.content) if self.graph_extractor else self._extract_graph(title, chunk.content)
            except (httpx.HTTPError, OSError, ValueError):
                extracted_entities, extracted_relations = self._extract_graph(title, chunk.content)
            for label, kind in extracted_entities:
                label = canonical_graph_label(label)
                if label: entity_kinds.setdefault(label, kind)
            for source, target, relation in extracted_relations:
                source, target, relation = canonical_graph_label(source), canonical_graph_label(target), canonical_graph_relation(relation)
                if not source or not target or source == target or (has_outline and (source == topic or target == topic)):
                    continue
                key = (source, target, relation, chunk.id)
                if key not in seen:
                    seen.add(key); relations.append((source, target, relation, chunk.id, 0.75 if self.graph_extractor else 0.35))
        return list(entity_kinds.items()), relations

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
