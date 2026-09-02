"""Adaptive semantic document splitting backed by a local embedding model."""

from __future__ import annotations

import math
import re

from iris_agent.knowledge.chunker import ChunkDraft, chunk_text
from iris_agent.knowledge.embedder import EmbeddingError, OllamaEmbedder


class SemanticSplitError(RuntimeError):
    """The local semantic splitter could not produce safe chunks."""


class LocalSemanticSplitter:
    """Find topic boundaries locally while deferring structured documents to the normal chunker."""

    def __init__(
        self,
        embedder: OllamaEmbedder,
        *,
        similarity_threshold: float = 0.58,
        minimum_input_chars: int = 600,
        owns_embedder: bool = False,
    ) -> None:
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if minimum_input_chars < 1:
            raise ValueError("minimum_input_chars must be positive")
        self.embedder = embedder
        self.model = embedder.model
        self.base_url = embedder.base_url
        self.similarity_threshold = float(similarity_threshold)
        self.minimum_input_chars = minimum_input_chars
        self._owns_embedder = owns_embedder

    def split(self, title: str, text: str, *, target_chars: int) -> list[ChunkDraft]:
        del title  # The splitter preserves source text and does not need to prompt a language model.
        if not isinstance(text, str) or not text.strip():
            return []
        if target_chars < 1:
            raise ValueError("target_chars must be positive")
        if len(text) < max(self.minimum_input_chars, int(target_chars * 1.25)):
            return []
        if self._has_explicit_structure(text):
            return []

        units = self._units(text)
        if len(units) < 2:
            return []
        try:
            vectors = self.embedder.embed([unit.strip() for unit in units])
        except EmbeddingError as exc:
            raise SemanticSplitError(f"本地语义拆分失败: {exc}") from exc
        if len(vectors) != len(units):
            raise SemanticSplitError("本地语义拆分返回的向量数量不匹配")

        similarities = [self._cosine(vectors[index - 1], vectors[index]) for index in range(1, len(vectors))]
        minimum_chunk_chars = max(1, int(target_chars * 0.45))
        groups: list[str] = []
        current = units[0]
        for index, unit in enumerate(units[1:], start=1):
            topic_changed = similarities[index - 1] < self.similarity_threshold
            target_reached = len(current) + len(unit) > target_chars
            if len(current) >= minimum_chunk_chars and (topic_changed or target_reached):
                groups.append(current)
                current = unit
            else:
                current += unit
        if current:
            groups.append(current)

        drafts: list[ChunkDraft] = []
        for group in groups:
            drafts.extend(chunk_text(group, location=None, target_chars=target_chars, overlap_chars=0, _semantic=False))
        if len(drafts) < 2 or "".join(draft.content for draft in drafts) != text:
            return []
        return drafts

    @staticmethod
    def _has_explicit_structure(text: str) -> bool:
        heading = re.compile(
            r"(?m)^\s*(?:#{1,6}\s+.+|(?:第[一二三四五六七八九十百\d]+[章节题]|问题\s*\d+|\d+(?:\.\d+){0,4}[、.])\s*.+)\s*$"
        )
        return heading.search(text) is not None

    @staticmethod
    def _units(text: str) -> list[str]:
        return [unit for unit in re.findall(r".+?(?:\n\s*\n|[。！？!?]+|$)", text, flags=re.DOTALL) if unit.strip()]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            raise SemanticSplitError("本地语义拆分返回的向量维度不匹配")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)

    def close(self) -> None:
        if self._owns_embedder:
            self.embedder._client.close()
