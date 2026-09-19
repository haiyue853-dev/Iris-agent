import json
from pathlib import Path

from iris_agent.config.settings import TtsSettings
from iris_agent.tts.client import GptSovitsClient
from iris_agent.tts.emotion import VoiceReference


WAV = b"RIFF" + (b"\x00" * 4) + b"WAVEfmt " + (b"\x00" * 40)


class Response:
    headers = {"Content-Type": "audio/wav"}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _limit: int | None = None) -> bytes:
        return self.body


def test_synthesize_sends_cross_language_reference_payload() -> None:
    requests = []

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response(WAV)

    settings = TtsSettings(
        enabled=True,
        base_url="http://127.0.0.1:9880",
        reference_audio_path=Path("D:/AI/tomori/ref.mp3"),
        reference_text="高松燈、です。よろしく……",
        reference_language="ja",
        target_language="zh",
        request_timeout_seconds=123,
    )
    client = GptSovitsClient(settings, open_url=open_request)

    assert client.synthesize("你好，我是高松灯。") == WAV
    request, timeout = requests[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://127.0.0.1:9880/tts"
    assert timeout == 123
    assert payload["text"] == "你好，我是高松灯。"
    assert payload["text_lang"] == "zh"
    assert payload["prompt_text"] == "高松燈、です。よろしく……"
    assert payload["prompt_lang"] == "ja"
    assert payload["ref_audio_path"] == "D:\\AI\\tomori\\ref.mp3"
    assert payload["streaming_mode"] is False
    assert payload["media_type"] == "wav"
    assert payload["top_k"] == 10
    assert payload["top_p"] == 0.8
    assert payload["temperature"] == 0.7


def test_synthesize_uses_emotional_primary_and_auxiliary_references() -> None:
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return Response(WAV)

    settings = TtsSettings(enabled=True, base_url="http://127.0.0.1:9880")
    client = GptSovitsClient(settings, open_url=open_request)
    reference = VoiceReference(Path("D:/AI/tomori/happy.mp3"), "嬉しい！", "happy")

    assert client.synthesize(
        "太好了！",
        reference,
        (Path("D:/AI/tomori/happy-2.mp3"),),
    ) == WAV

    payload = json.loads(requests[0].data.decode("utf-8"))
    assert payload["ref_audio_path"] == "D:\\AI\\tomori\\happy.mp3"
    assert payload["prompt_text"] == "嬉しい！"
    assert payload["aux_ref_audio_paths"] == ["D:\\AI\\tomori\\happy-2.mp3"]
