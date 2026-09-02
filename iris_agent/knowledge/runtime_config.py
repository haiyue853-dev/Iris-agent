"""Persistent, non-secret runtime settings for the RAG model pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


RUNTIME_MODEL_FIELDS = (
    "embedding_enabled", "embedding_model", "embedding_base_url",
    "semantic_split_enabled", "semantic_split_model", "semantic_split_base_url",
    "graph_enabled", "graph_model", "graph_base_url",
    "image_enabled", "image_model", "image_base_url",
    "reranker_enabled", "reranker_provider", "reranker_model", "reranker_base_url",
    "mmr_relevance_weight",
)
_BOOLEAN_FIELDS = {field for field in RUNTIME_MODEL_FIELDS if field.endswith("_enabled")}
_URL_FIELDS = {field for field in RUNTIME_MODEL_FIELDS if field.endswith("_base_url")}
_MODEL_FIELDS = {field for field in RUNTIME_MODEL_FIELDS if field.endswith("_model")}


def normalise_runtime_config(values: dict, defaults: dict) -> dict:
    if not isinstance(values, dict) or not isinstance(defaults, dict):
        raise ValueError("RAG 运行配置必须是对象")
    merged = {field: values.get(field, defaults.get(field)) for field in RUNTIME_MODEL_FIELDS}
    for field in _BOOLEAN_FIELDS:
        if not isinstance(merged[field], bool):
            raise ValueError(f"{field} 必须是布尔值")
    for field in _MODEL_FIELDS:
        value = merged[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} 不能为空")
        merged[field] = value.strip()
    for field in _URL_FIELDS:
        value = merged[field]
        if not isinstance(value, str):
            raise ValueError(f"{field} 必须是 HTTP(S) 地址")
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{field} 必须是 HTTP(S) 地址")
        merged[field] = value
    provider = merged.get("reranker_provider")
    if provider not in {"ollama", "api", "fastembed", "none"}:
        raise ValueError("reranker_provider 必须是 ollama、api、fastembed 或 none")
    if provider == "none":
        merged["reranker_enabled"] = False
    weight = merged["mmr_relevance_weight"]
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
        raise ValueError("mmr_relevance_weight 必须在 0 到 1 之间")
    merged["mmr_relevance_weight"] = float(weight)
    return merged


def load_runtime_config(path: Path, defaults: dict) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("RAG 运行配置文件无法读取") from exc
    return normalise_runtime_config(payload, defaults)


def save_runtime_config(path: Path, values: dict, defaults: dict) -> dict:
    config = normalise_runtime_config(values, defaults)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ValueError("RAG 运行配置无法保存") from exc
    return config
