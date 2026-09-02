import json

import httpx
import pytest

from iris_agent.knowledge.reranking import build_reranker
from iris_agent.knowledge.reranking.api_reranker import HttpApiReranker
from iris_agent.knowledge.reranking.fastembed_reranker import FastEmbedReranker
from iris_agent.knowledge.reranker import OllamaReranker


def test_api_reranker_uses_standard_rerank_contract():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request, json.loads(request.content)))
        return httpx.Response(200, json={"results": [
            {"index": 1, "relevance_score": 0.92},
            {"index": 0, "relevance_score": 0.31},
        ]})

    reranker = build_reranker(
        "api",
        model="BAAI/bge-reranker-v2-m3",
        base_url="https://rerank.test/v1",
        api_key="secret",
    )
    assert isinstance(reranker, HttpApiReranker)
    reranker.client.close()
    reranker.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer secret"},
    )
    try:
        scores = reranker.score("RAG", [("a", "普通内容"), ("b", "RAG 检索内容")])
    finally:
        reranker.close()

    request, payload = requests[0]
    assert str(request.url) == "https://rerank.test/v1/rerank"
    assert request.headers["Authorization"] == "Bearer secret"
    assert payload["documents"] == ["普通内容", "RAG 检索内容"]
    assert scores == {"b": 0.92, "a": 0.31}


def test_none_reranker_provider_disables_reranking():
    assert build_reranker("none", model="unused") is None


def test_fastembed_reranker_batches_candidates_and_normalizes_logits(monkeypatch):
    calls = []

    class Encoder:
        def rerank(self, query, documents):
            calls.append((query, documents))
            return [0.0, 2.0]

    monkeypatch.setattr(FastEmbedReranker, "_load_encoder", lambda self: Encoder())
    reranker = build_reranker("fastembed", model="BAAI/bge-reranker-base")
    try:
        scores = reranker.score("RAG", [("a", "普通内容"), ("b", "RAG 检索内容")])
    finally:
        reranker.close()

    assert isinstance(reranker, FastEmbedReranker)
    assert calls == [("RAG", ["普通内容", "RAG 检索内容"])]
    assert scores["a"] == pytest.approx(0.5)
    assert scores["b"] == pytest.approx(0.880797, rel=1e-5)


def test_fastembed_uses_quantized_onnx_file_for_bge_v2_m3():
    options = FastEmbedReranker.custom_model_options("onnx-community/bge-reranker-v2-m3-ONNX")

    assert options["model_file"] == "onnx/model_quantized.onnx"
    assert "tokenizer.json" in options["additional_files"]
    assert options["size_in_gb"] == pytest.approx(0.58)


def test_local_ollama_reranker_does_not_use_environment_proxy(monkeypatch):
    client_options = {}

    class Client:
        def __init__(self, **kwargs):
            client_options.update(kwargs)

        def close(self):
            return None

    monkeypatch.setattr("iris_agent.knowledge.reranker.httpx.Client", Client)

    reranker = OllamaReranker(model="deepseek-r1:8b", base_url="http://localhost:11434")
    reranker.close()

    assert client_options["trust_env"] is False


def test_local_ollama_reranker_uses_strict_schema_and_disables_thinking():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"response": json.dumps({"scores": [
            {"index": 1, "score": 0.95}, {"index": 2, "score": 0.1},
        ]})})

    reranker = OllamaReranker(model="qwen3.5:4b", base_url="http://localhost:11434")
    reranker.client.close()
    reranker.client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        scores = reranker.score("如何自动重连？", [("a", "SSE 支持自动重连"), ("b", "Redis 缓存")])
    finally:
        reranker.close()

    payload = requests[0]
    assert payload["think"] is False
    assert payload["format"]["properties"]["scores"]["minItems"] == 2
    assert payload["format"]["properties"]["scores"]["maxItems"] == 2
    assert scores == {"a": 0.95, "b": 0.1}
