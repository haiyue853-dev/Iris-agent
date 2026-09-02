import json

import httpx

from iris_agent.knowledge.parsing.vision import OllamaImageDescriber


def test_ollama_image_describer_sends_image_and_returns_indexable_text():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "图中显示用户问题经过向量检索后进入重排器"})

    describer = OllamaImageDescriber(model="qwen-vl", base_url="http://ollama.test")
    describer.client.close()
    describer.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = describer.describe(b"image", "pipeline.png")
    finally:
        describer.close()

    assert result == "图中显示用户问题经过向量检索后进入重排器"
    assert requests[0]["model"] == "qwen-vl"
    assert requests[0]["images"] == ["aW1hZ2U="]
    assert "pipeline.png" in requests[0]["prompt"]
