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
        self._client = http_client or httpx.Client(timeout=timeout, trust_env=False)

    def embed(self, texts: str | list[str]) -> list[list[float]]:
        inputs = [texts] if isinstance(texts, str) else list(texts)
        if not inputs:
            return []
        try:
            response = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": inputs},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings") if isinstance(data, dict) else None
            if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
                raise EmbeddingError("embedding 返回格式异常")
            return embeddings
        except Exception as batch_error:
            try:
                embeddings = []
                for text in inputs:
                    response = self._client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    response.raise_for_status()
                    data = response.json()
                    vector = data.get("embedding") if isinstance(data, dict) else None
                    if not isinstance(vector, list) or not vector:
                        raise EmbeddingError("兼容 embedding 返回格式异常")
                    embeddings.append(vector)
                return embeddings
            except Exception as legacy_error:
                raise EmbeddingError(
                    f"embedding 调用失败: {batch_error}; 兼容接口也失败: {legacy_error}"
                ) from legacy_error
