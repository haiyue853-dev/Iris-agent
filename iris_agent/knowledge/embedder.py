"""Ollama embedding client: turn text into vectors via the local Ollama /api/embed endpoint."""

from __future__ import annotations

import httpx


class EmbeddingError(RuntimeError):
    """The local embedding service could not produce vectors."""


class OllamaEmbedder:
    def __init__(
        self,
        model: str = "bge-m3",
        base_url: str = "http://localhost:11434",
        timeout: float = 60,
        http_client: httpx.Client | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client or httpx.Client(timeout=timeout)

    def embed(self, texts: str | list[str]) -> list[list[float]]:
        inputs = [texts] if isinstance(texts, str) else list(texts)
        try:
            response = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": inputs},
            )
            response.raise_for_status()
            data = response.json()
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"embedding 调用失败: {exc}") from exc
        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
            raise EmbeddingError("embedding 返回格式异常")
        return embeddings
