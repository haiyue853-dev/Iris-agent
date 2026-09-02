"""OllamaEmbedder tests: payload, parsing, error handling."""

from __future__ import annotations

import pytest

from iris_agent.knowledge.embedder import EmbeddingError, OllamaEmbedder


class FakeResponse:
    def __init__(self, data=None, status_error=None):
        self._data = data
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, json=None):
        self.calls.append((url, json))
        return self._response


def test_embed_returns_vectors():
    client = FakeClient(FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]}))
    embedder = OllamaEmbedder(http_client=client)
    assert embedder.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_accepts_single_string():
    client = FakeClient(FakeResponse({"embeddings": [[0.1]]}))
    embedder = OllamaEmbedder(http_client=client)
    assert embedder.embed("a") == [[0.1]]


def test_embed_sends_correct_payload():
    client = FakeClient(FakeResponse({"embeddings": [[0.1]]}))
    embedder = OllamaEmbedder(model="bge-m3", base_url="http://localhost:11434", http_client=client)
    embedder.embed("hello")
    url, payload = client.calls[0]
    assert url == "http://localhost:11434/api/embed"
    assert payload == {"model": "bge-m3", "input": ["hello"]}


def test_embed_raises_on_http_error():
    class HttpError(Exception):
        pass

    client = FakeClient(FakeResponse(status_error=HttpError("boom")))
    embedder = OllamaEmbedder(http_client=client)
    with pytest.raises(EmbeddingError):
        embedder.embed("a")


def test_embed_raises_on_malformed_response():
    client = FakeClient(FakeResponse({"embeddings": [[0.1]]}))
    embedder = OllamaEmbedder(http_client=client)
    with pytest.raises(EmbeddingError):
        embedder.embed(["a", "b"])


def test_embed_falls_back_to_legacy_endpoint_when_batch_endpoint_fails():
    class CompatibleClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None):
            self.calls.append((url, json))
            if url.endswith("/api/embed"):
                return FakeResponse(status_error=RuntimeError("502 Bad Gateway"))
            return FakeResponse({"embedding": [float(len(json["prompt"]))]})

    client = CompatibleClient()
    embedder = OllamaEmbedder(model="bge-m3", base_url="http://localhost:11434", http_client=client)

    assert embedder.embed(["one", "three"]) == [[3.0], [5.0]]
    assert client.calls == [
        ("http://localhost:11434/api/embed", {"model": "bge-m3", "input": ["one", "three"]}),
        ("http://localhost:11434/api/embeddings", {"model": "bge-m3", "prompt": "one"}),
        ("http://localhost:11434/api/embeddings", {"model": "bge-m3", "prompt": "three"}),
    ]
