from __future__ import annotations

import json

import pytest

from iris_agent.bootstrap import _rag_runtime_defaults
from iris_agent.config.settings import Settings
from iris_agent.knowledge.runtime_config import load_runtime_config, normalise_runtime_config, save_runtime_config


def _defaults() -> dict:
    return {
        "embedding_enabled": True,
        "embedding_model": "bge-m3",
        "embedding_base_url": "http://localhost:11434",
        "semantic_split_enabled": False,
        "semantic_split_model": "bge-m3",
        "semantic_split_base_url": "http://localhost:11434",
        "graph_enabled": True,
        "graph_model": "deepseek-r1:8b",
        "graph_base_url": "http://localhost:11434",
        "image_enabled": False,
        "image_model": "qwen2.5vl:7b",
        "image_base_url": "http://localhost:11434",
        "reranker_enabled": True,
        "reranker_provider": "ollama",
        "reranker_model": "deepseek-r1:8b",
        "reranker_base_url": "http://localhost:11434",
        "mmr_relevance_weight": 0.7,
    }


def test_runtime_config_round_trip_uses_only_supported_fields(tmp_path):
    path = tmp_path / "runtime.json"
    config = {**_defaults(), "embedding_model": "nomic-embed-text", "unknown": "ignored"}

    saved = save_runtime_config(path, config, _defaults())

    assert saved["embedding_model"] == "nomic-embed-text"
    assert "unknown" not in saved
    assert load_runtime_config(path, _defaults()) == saved
    assert json.loads(path.read_text(encoding="utf-8")) == saved


def test_runtime_config_persists_mmr_relevance_weight(tmp_path):
    saved = save_runtime_config(
        tmp_path / "runtime.json",
        {**_defaults(), "mmr_relevance_weight": 0.4},
        _defaults(),
    )

    assert saved.get("mmr_relevance_weight") == 0.4


def test_application_runtime_defaults_include_a_valid_mmr_weight():
    defaults = _rag_runtime_defaults(Settings())

    assert defaults["mmr_relevance_weight"] == 0.7


def test_none_reranker_provider_disables_reranking(tmp_path):
    saved = save_runtime_config(
        tmp_path / "runtime.json",
        {**_defaults(), "reranker_provider": "none", "reranker_enabled": True},
        _defaults(),
    )

    assert saved["reranker_enabled"] is False


def test_fastembed_reranker_provider_is_supported():
    config = normalise_runtime_config(
        {**_defaults(), "reranker_provider": "fastembed", "reranker_model": "BAAI/bge-reranker-base"},
        _defaults(),
    )

    assert config["reranker_provider"] == "fastembed"


@pytest.mark.parametrize("field,value", [
    ("embedding_base_url", "file:///tmp/model"),
    ("reranker_provider", "mystery"),
    ("image_model", "  "),
    ("graph_enabled", "true"),
])
def test_runtime_config_rejects_invalid_values(tmp_path, field, value):
    with pytest.raises(ValueError):
        save_runtime_config(tmp_path / "runtime.json", {**_defaults(), field: value}, _defaults())
