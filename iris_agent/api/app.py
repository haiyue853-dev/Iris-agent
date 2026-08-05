import json
import logging
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError

from iris_agent.api.report_schemas import (
    GenerateReportRequest,
    RestoreReportRequest,
    ReviseReportRequest,
    SaveReportRequest,
)
from iris_agent.api.schemas import ChatRequest, CreateSessionRequest
from iris_agent.core.agent import AgentService
from iris_agent.core.errors import IrisError, SessionNotFoundError
from iris_agent.reports.errors import (
    ReportGenerationError,
    ReportNotFoundError,
    ReportStorageError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.models import DailyReport, ReportVersion
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.base import Session, SessionRepository

logger = logging.getLogger(__name__)


def _session_data(session: Session, include_messages: bool = True) -> dict:
    data = {"id": session.id, "name": session.name, "created_at": session.created_at, "updated_at": session.updated_at}
    if include_messages:
        data["messages"] = [{"role": message.role, "content": message.content} for message in session.messages if message.role in {"user", "assistant"}]
    return data


def _version_data(version: ReportVersion, include_sections: bool = True) -> dict:
    data = {
        "number": version.number,
        "kind": version.kind,
        "instruction": version.instruction,
        "created_at": version.created_at,
    }
    if include_sections:
        data["sections"] = version.sections.to_dict()
    return data


def _report_data(report: DailyReport) -> dict:
    return {
        "date": report.date,
        "source_notes": report.source_notes,
        "source_session_id": report.source_session_id,
        "current_version": report.current_version,
        "current": _version_data(report.current),
        "versions": [_version_data(item, include_sections=False) for item in report.versions],
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def _report_summary(report: DailyReport) -> dict:
    completed = report.current.sections.completed
    return {
        "date": report.date,
        "summary": completed[0] if completed else "暂无内容",
        "current_version": report.current_version,
        "updated_at": report.updated_at,
    }


def create_app(
    service: AgentService,
    sessions: SessionRepository,
    reports: DailyReportService | None = None,
) -> FastAPI:
    app = FastAPI(title="Iris Agent API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(IrisError)
    async def iris_error_handler(_, exc: IrisError):
        if isinstance(exc, (SessionNotFoundError, ReportNotFoundError)):
            code = 404
        elif isinstance(exc, ReportVersionConflictError):
            code = 409
        elif isinstance(exc, ReportValidationError):
            code = 422
        elif isinstance(exc, ReportGenerationError) and exc.code == "report_model_output_invalid":
            code = 422
        elif isinstance(exc, (ReportGenerationError, ReportStorageError)):
            code = 500
        else:
            code = 500
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

    if reports is not None:
        @app.get("/api/reports")
        def list_reports():
            return {"reports": [_report_summary(item) for item in reports.list_reports()]}

        @app.post("/api/reports/generate", status_code=status.HTTP_201_CREATED)
        def generate_report(request: GenerateReportRequest):
            return _report_data(
                reports.generate(
                    request.date,
                    request.notes,
                    request.session_id,
                    request.include_chat,
                    request.expected_version,
                )
            )

        @app.get("/api/reports/{report_date}")
        def get_report(report_date: str):
            return _report_data(reports.get_report(report_date))

        @app.get("/api/reports/{report_date}/versions/{version}")
        def get_report_version(report_date: str, version: int):
            return _version_data(reports.get_version(report_date, version))

        @app.put("/api/reports/{report_date}")
        def save_report(report_date: str, request: SaveReportRequest):
            return _report_data(
                reports.save_manual(report_date, request.sections.to_model(), request.expected_version)
            )

        @app.post("/api/reports/{report_date}/revise")
        def revise_report(report_date: str, request: ReviseReportRequest):
            return _report_data(
                reports.revise(report_date, request.instruction, request.expected_version)
            )

        @app.post("/api/reports/{report_date}/versions/{version}/restore")
        def restore_report(report_date: str, version: int, request: RestoreReportRequest):
            return _report_data(
                reports.restore(report_date, version, request.expected_version)
            )

        @app.get("/api/reports/{report_date}/download")
        def download_report(report_date: str, version: int | None = None):
            markdown = reports.render_markdown(report_date, version)
            encoded_name = quote(f"日报-{report_date}.md")
            disposition = (
                f'attachment; filename="report-{report_date}.md"; '
                f"filename*=UTF-8''{encoded_name}"
            )
            return Response(
                content=markdown.encode("utf-8"),
                media_type="text/markdown",
                headers={"Content-Disposition": disposition},
            )

    return app
