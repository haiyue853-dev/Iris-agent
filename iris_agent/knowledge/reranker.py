"""Local LLM reranking for the final RAG candidate set."""

from __future__ import annotations

import json

import httpx


class OllamaReranker:
    """Scores a small candidate set with a local chat model in one request."""

    def __init__(self, *, model: str = "deepseek-r1:8b", base_url: str, timeout: float = 60) -> None:
        self.model, self.base_url = model.strip(), base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, trust_env=False)

    def score(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        if not candidates:
            return {}
        candidate_count = len(candidates)
        corpus = "\n\n".join(f"[{index}] {content[:700]}" for index, (_, content) in enumerate(candidates, 1))
        prompt = f"""你是知识库检索重排器。对每个候选片段打分，必须返回 index 1 到 {candidate_count} 的全部评分，不得遗漏。
分数范围 0 到 1；只按片段是否能直接、准确回答问题评分，不要解释。
问题：{query[:500]}
候选片段：
{corpus}"""
        score_schema = {
            "type": "object",
            "properties": {"scores": {
                "type": "array", "minItems": candidate_count, "maxItems": candidate_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "minimum": 1, "maximum": candidate_count},
                        "score": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["index", "score"],
                },
            }},
            "required": ["scores"],
        }
        response = self.client.post(f"{self.base_url}/api/generate", json={
            "model": self.model, "prompt": prompt, "format": score_schema, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": max(256, candidate_count * 48)},
        })
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response") or payload.get("thinking") or ""
        parsed = json.loads(raw)
        values: dict[str, float] = {}
        for item in parsed.get("scores", []) if isinstance(parsed.get("scores"), list) else []:
            if not isinstance(item, dict):
                continue
            index, score = item.get("index"), item.get("score")
            if isinstance(index, int) and 1 <= index <= len(candidates):
                try:
                    values[candidates[index - 1][0]] = max(0.0, min(float(score), 1.0))
                except (TypeError, ValueError):
                    continue
        return values

    def close(self) -> None:
        self.client.close()
