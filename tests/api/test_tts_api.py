from fastapi import FastAPI
from fastapi.testclient import TestClient

from iris_agent.api.tts_api import register_tts_routes
from iris_agent.tts.errors import TtsMessageError


WAV = b"RIFF" + (b"\x00" * 4) + b"WAVEfmt " + (b"\x00" * 40)


class FakeTts:
    def status(self) -> dict[str, str]:
        return {"status": "ready", "detail": "", "emotion": "enabled"}

    def synthesize_message(self, session_id: str, message_id: str) -> bytes:
        if message_id == "message_wrong":
            raise TtsMessageError("只能朗读助手回复")
        assert session_id == "session_test"
        assert message_id == "message_ok"
        return WAV


def test_message_speech_route_returns_wav() -> None:
    app = FastAPI()
    register_tts_routes(app, FakeTts())

    response = TestClient(app).post(
        "/api/tts/sessions/session_test/messages/message_ok"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == WAV


def test_message_speech_route_maps_message_error_to_conflict() -> None:
    app = FastAPI()
    register_tts_routes(app, FakeTts())

    response = TestClient(app).post(
        "/api/tts/sessions/session_test/messages/message_wrong"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "只能朗读助手回复"


def test_tts_status_route_exposes_warmup_state() -> None:
    app = FastAPI()
    register_tts_routes(app, FakeTts())

    response = TestClient(app).get("/api/tts/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "detail": "", "emotion": "enabled"}
