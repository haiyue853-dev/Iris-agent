import json
import logging

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError

from iris_agent.api.schemas import ChatRequest, CreateSessionRequest
from iris_agent.core.agent import AgentService
from iris_agent.core.errors import IrisError, SessionNotFoundError
from iris_agent.sessions.base import Session, SessionRepository

logger = logging.getLogger(__name__)


def _session_data(session: Session, include_messages: bool = True) -> dict:
    data = {"id": session.id, "name": session.name, "created_at": session.created_at, "updated_at": session.updated_at}
    if include_messages:
        data["messages"] = [{"role": message.role, "content": message.content} for message in session.messages if message.role in {"user", "assistant"}]
    return data


def create_app(service: AgentService, sessions: SessionRepository, reports=None) -> FastAPI:
    app = FastAPI(title="Iris Agent API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(IrisError)
    async def iris_error_handler(_, exc: IrisError):
        code = 404 if isinstance(exc, SessionNotFoundError) else 500
        return Response(content=json.dumps({"detail": {"code": exc.code, "message": exc.safe_message}}, ensure_ascii=False), status_code=code, media_type="application/json")

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, __):
        return Response(content=json.dumps({"detail": {"code": "validation_error", "message": "请求参数无效"}}, ensure_ascii=False), status_code=422, media_type="application/json")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(request: CreateSessionRequest):
        return _session_data(sessions.create(request.name), include_messages=False)

    @app.get("/api/sessions")
    def list_sessions():
        return {"sessions": [_session_data(item, include_messages=False) for item in sessions.list()]}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        return _session_data(sessions.get(session_id))

    @app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_session(session_id: str):
        sessions.delete(session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/sessions/{session_id}/reset")
    def reset_session(session_id: str):
        return _session_data(sessions.clear(session_id))

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest):
        sessions.get(request.session_id)

        def generate():
            try:
                for event in service.run(request.session_id, request.message):
                    yield json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            except IrisError as exc:
                yield json.dumps({"type": "error", "data": {"code": exc.code, "message": exc.safe_message}}, ensure_ascii=False) + "\n"
            except Exception:
                logger.exception("流式对话发生未处理异常")
                yield json.dumps({"type": "error", "data": {"code": "internal_error", "message": "服务内部错误"}}, ensure_ascii=False) + "\n"

        return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
