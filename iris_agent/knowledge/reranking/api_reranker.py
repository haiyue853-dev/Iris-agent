"""Reranking over the de-facto standard HTTP /rerank contract (Jina / SiliconFlow / Cohere-compatible)."""

from __future__ import annotations

import httpx


class HttpApiReranker:
    """Posts {model, query, documents} to a rerank endpoint and maps scores back to chunk ids."""

    def __init__(self, *, model: str, base_url: str | None = None, api_key: str | None = None, timeout: float = 60):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("rerank model must be non-blank")
        self.model = model.strip()
        endpoint = (base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("rerank base URL must be http(s)")
        self.endpoint = endpoint if endpoint.endswith("/rerank") else f"{endpoint}/rerank"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def score(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        if not candidates:
            return {}
        response = self.client.post(self.endpoint, json={
            "model": self.model,
            "query": query,
            "documents": [content for _, content in candidates],
            "top_n": len(candidates),
            "return_documents": False,
        })
        response.raise_for_status()
        payload = response.json()
        values: dict[str, float] = {}
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            index, score = item.get("index"), item.get("relevance_score", item.get("score"))
            if isinstance(index, int) and 0 <= index < len(candidates):
                try:
                    values[candidates[index][0]] = max(0.0, min(float(score), 1.0))
                except (TypeError, ValueError):
                    continue
        return values

    def close(self) -> None:
        self.client.close()
