from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, StreamingResponse

from iris_agent.tts.errors import (
    TtsDisabledError,
    TtsError,
    TtsMessageError,
    TtsMessageNotFoundError,
    TtsTimeoutError,
    TtsTooLargeError,
    TtsUnavailableError,
    TtsUpstreamError,
)
from iris_agent.tts.service import TtsService


def register_tts_routes(app: FastAPI, tts: TtsService) -> None:
    @app.get("/api/tts/status")
    def tts_status() -> dict[str, str]:
        return tts.status()

    @app.post("/api/tts/sessions/{session_id}/messages/{message_id}")
    def synthesize_message(session_id: str, message_id: str) -> Response:
        try:
            audio = tts.synthesize_message(session_id, message_id)
        except TtsError as exc:
            return JSONResponse(
                status_code=_status_code(exc),
                content={"detail": {"code": exc.code, "message": exc.safe_message}},
            )
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.get("/api/tts/sessions/{session_id}/messages/{message_id}/stream")
    def stream_message(session_id: str, message_id: str) -> Response:
        try:
            audio = tts.stream_message(session_id, message_id)
        except TtsError as exc:
            return JSONResponse(
                status_code=_status_code(exc),
                content={"detail": {"code": exc.code, "message": exc.safe_message}},
            )
        return StreamingResponse(
            audio,
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=86400"},
        )


def _status_code(error: TtsError) -> int:
    if isinstance(error, TtsMessageNotFoundError):
        return 404
    if isinstance(error, TtsMessageError):
        return 409
    if isinstance(error, TtsTooLargeError):
        return 413
    if isinstance(error, (TtsDisabledError, TtsUnavailableError)):
        return 503
    if isinstance(error, TtsTimeoutError):
        return 504
    if isinstance(error, TtsUpstreamError):
        return 502
    return 500
