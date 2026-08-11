"""Atomic local persistence for generated document drafts."""

from __future__ import annotations

from dataclasses import replace
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable
from uuid import UUID, uuid4

from iris_agent.documents.errors import (
    DocumentDraftNotFoundError,
    DocumentRevisionConflictError,
    DocumentStorageError,
    DocumentValidationError,
)
from iris_agent.documents.models import DOCUMENT_TEMPLATES, DocumentCitation, DocumentDraft


class DraftRepository:
    """Stores draft metadata and rendered Markdown independently from uploaded source files."""

    def __init__(self, root: str | Path, *, clock: Callable[[], float] = time.time):
        self._lock = threading.RLock()
        self._clock = clock
        self._drafts: dict[str, DocumentDraft] = {}
        try:
            requested_root = Path(root)
            if requested_root.is_symlink() or not requested_root.is_dir():
                raise OSError("unsafe document root")
            self._root = requested_root.resolve(strict=True)
            directory = self._root / "drafts"
            if directory.exists() and directory.is_symlink():
                raise OSError("unsafe drafts directory")
            directory.mkdir(exist_ok=True)
            self._directory = directory.resolve(strict=True)
            if self._directory.parent != self._root or not self._directory.is_dir():
                raise OSError("drafts directory escaped root")
            self._index_path = self._directory / "index.json"
            self._load()
        except DocumentStorageError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DocumentStorageError("无法准备文档草稿存储") from exc

    def create(
        self,
        *,
        title: str,
        template: str,
        document_ids: tuple[str, ...],
        instructions: str,
        markdown: str,
        citations: tuple[DocumentCitation, ...],
    ) -> DocumentDraft:
        with self._lock:
            now = self._clock()
            try:
                draft = DocumentDraft(
                    id=str(uuid4()),
                    title=title,
                    template=template,  # type: ignore[arg-type]
                    document_ids=document_ids,
                    instructions=instructions,
                    markdown=markdown,
                    citations=citations,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
            except ValueError as exc:
                raise DocumentValidationError("文档草稿内容无效") from exc
            self._drafts[draft.id] = draft
            try:
                self._write_index()
            except DocumentStorageError:
                self._drafts.pop(draft.id, None)
                raise
            return draft

    def list(self) -> list[DocumentDraft]:
        with self._lock:
            return sorted(self._drafts.values(), key=lambda item: (item.updated_at, item.id), reverse=True)

    def get(self, draft_id: str) -> DocumentDraft:
        with self._lock:
            self._validate_id(draft_id)
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise DocumentDraftNotFoundError("文档草稿不存在")
            return draft

    def update(self, draft_id: str, *, title: str, markdown: str, expected_revision: int) -> DocumentDraft:
        with self._lock:
            current = self.get(draft_id)
            if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
                raise DocumentValidationError("草稿版本无效")
            if expected_revision != current.revision:
                raise DocumentRevisionConflictError("草稿已被其他操作更新，请刷新后重试")
            try:
                updated = replace(
                    current,
                    title=title,
                    markdown=markdown,
                    revision=current.revision + 1,
                    updated_at=self._clock(),
                )
            except ValueError as exc:
                raise DocumentValidationError("文档草稿内容无效") from exc
            self._drafts[draft_id] = updated
            try:
                self._write_index()
            except DocumentStorageError:
                self._drafts[draft_id] = current
                raise
            return updated

    def _load(self) -> None:
        if self._index_path.is_symlink():
            raise DocumentStorageError("无法访问文档草稿存储")
        if not self._index_path.exists():
            self._write_index()
            return
        self._assert_index_file()
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DocumentStorageError("无法读取文档草稿索引") from exc
        if not isinstance(raw, dict) or set(raw) != {"drafts"} or not isinstance(raw["drafts"], list):
            raise DocumentStorageError("无法读取文档草稿索引")
        drafts: dict[str, DocumentDraft] = {}
        for encoded in raw["drafts"]:
            draft = self._decode(encoded)
            if draft.id in drafts:
                raise DocumentStorageError("无法读取文档草稿索引")
            drafts[draft.id] = draft
        self._drafts = drafts

    def _write_index(self) -> None:
        payload = {"drafts": [self._encode(item) for item in self.list()]}
        try:
            self._atomic_write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
            self._assert_index_file()
        except DocumentStorageError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise DocumentStorageError("无法保存文档草稿索引") from exc

    @staticmethod
    def _encode(draft: DocumentDraft) -> dict[str, Any]:
        return {
            "id": draft.id,
            "title": draft.title,
            "template": draft.template,
            "document_ids": list(draft.document_ids),
            "instructions": draft.instructions,
            "markdown": draft.markdown,
            "citations": [
                {"document_id": citation.document_id, "location": citation.location}
                for citation in draft.citations
            ],
            "revision": draft.revision,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
        }

    @staticmethod
    def _decode(encoded: object) -> DocumentDraft:
        if not isinstance(encoded, dict) or set(encoded) != {
            "id", "title", "template", "document_ids", "instructions", "markdown", "citations",
            "revision", "created_at", "updated_at",
        }:
            raise DocumentStorageError("无法读取文档草稿索引")
        try:
            document_ids = encoded["document_ids"]
            citations = encoded["citations"]
            if not isinstance(document_ids, list) or not isinstance(citations, list):
                raise ValueError("invalid draft arrays")
            parsed_citations = tuple(
                DocumentCitation(document_id=item["document_id"], location=item["location"])
                for item in citations
                if isinstance(item, dict) and set(item) == {"document_id", "location"}
            )
            if len(parsed_citations) != len(citations):
                raise ValueError("invalid citations")
            return DocumentDraft(
                id=encoded["id"],
                title=encoded["title"],
                template=encoded["template"],
                document_ids=tuple(document_ids),
                instructions=encoded["instructions"],
                markdown=encoded["markdown"],
                citations=parsed_citations,
                revision=encoded["revision"],
                created_at=encoded["created_at"],
                updated_at=encoded["updated_at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DocumentStorageError("无法读取文档草稿索引") from exc

    def _atomic_write(self, content: bytes) -> None:
        temporary = self._directory / f".iris-draft-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._index_path)
        except OSError as exc:
            try:
                if temporary.exists() and not temporary.is_symlink():
                    temporary.unlink()
            except OSError:
                pass
            raise DocumentStorageError("无法写入文档草稿存储") from exc

    def _assert_index_file(self) -> None:
        if self._index_path.is_symlink() or not self._index_path.is_file():
            raise DocumentStorageError("无法访问文档草稿存储")
        try:
            resolved = self._index_path.resolve(strict=True)
        except OSError as exc:
            raise DocumentStorageError("无法访问文档草稿存储") from exc
        if resolved.parent != self._directory:
            raise DocumentStorageError("无法访问文档草稿存储")

    @staticmethod
    def _validate_id(draft_id: str) -> None:
        try:
            if str(UUID(draft_id)) != draft_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise DocumentDraftNotFoundError("文档草稿不存在") from None
