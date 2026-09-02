"""Reranker protocol and factory shared by all providers."""

from __future__ import annotations

from typing import Protocol

from iris_agent.knowledge.reranker import OllamaReranker


class RerankingError(RuntimeError):
    """A rerank request failed; callers should degrade to unranked candidates."""


class Reranker(Protocol):
    def score(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]: ...

    def close(self) -> None: ...


def build_reranker(
    provider: str,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 60,
) -> Reranker | None:
    """Resolve a rerank provider by name; ``none`` disables reranking."""
    from iris_agent.knowledge.reranking.api_reranker import HttpApiReranker

    normalized = (provider or "none").strip().lower()
    if normalized in {"none", "off", "disabled", ""}:
        return None
    if normalized == "api":
        return HttpApiReranker(model=model, base_url=base_url, api_key=api_key, timeout=timeout)
    if normalized == "ollama":
        if not base_url:
            raise ValueError("ollama reranker requires a base URL")
        return OllamaReranker(model=model, base_url=base_url, timeout=timeout)
    if normalized == "fastembed":
        from iris_agent.knowledge.reranking.fastembed_reranker import FastEmbedReranker
        return FastEmbedReranker(model=model)
    raise ValueError(f"未知的 rerank provider：{provider}")
