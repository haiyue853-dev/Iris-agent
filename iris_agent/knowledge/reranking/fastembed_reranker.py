from __future__ import annotations

import math
import threading


_CUSTOM_MODEL_LOCK = threading.Lock()
_CUSTOM_MODELS: dict[str, dict[str, object]] = {
    "onnx-community/bge-reranker-v2-m3-ONNX": {
        "model_file": "onnx/model_quantized.onnx",
        "additional_files": [
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ],
        "size_in_gb": 0.58,
    },
}


class FastEmbedReranker:
    """Lazy, batched ONNX cross-encoder backed by FastEmbed."""

    def __init__(self, *, model: str) -> None:
        self.model = model.strip()
        if not self.model:
            raise ValueError("fastembed reranker requires a model")
        self._encoder = None
        self._load_lock = threading.Lock()

    @staticmethod
    def custom_model_options(model: str) -> dict[str, object]:
        options = _CUSTOM_MODELS.get(model, {})
        result = dict(options)
        if "additional_files" in result:
            result["additional_files"] = list(result["additional_files"])
        return result

    def _load_encoder(self):
        try:
            from fastembed.common.model_description import ModelSource
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:
            raise ValueError("FastEmbed 未安装，请执行 pip install fastembed") from exc

        options = self.custom_model_options(self.model)
        if options:
            with _CUSTOM_MODEL_LOCK:
                supported = {item["model"] for item in TextCrossEncoder.list_supported_models()}
                if self.model not in supported:
                    TextCrossEncoder.add_custom_model(
                        model=self.model,
                        sources=ModelSource(hf=self.model),
                        **options,
                    )
        return TextCrossEncoder(model_name=self.model)

    def _get_encoder(self):
        if self._encoder is None:
            with self._load_lock:
                if self._encoder is None:
                    self._encoder = self._load_encoder()
        return self._encoder

    def score(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        if not candidates:
            return {}
        logits = list(self._get_encoder().rerank(query, [content for _, content in candidates]))
        if len(logits) != len(candidates):
            raise ValueError("FastEmbed 重排返回的分数数量不匹配")
        scores: dict[str, float] = {}
        for (candidate_id, _), raw in zip(candidates, logits):
            value = float(raw)
            probability = 1.0 / (1.0 + math.exp(-value)) if value >= 0 else math.exp(value) / (1.0 + math.exp(value))
            scores[candidate_id] = probability
        return scores

    def close(self) -> None:
        self._encoder = None
