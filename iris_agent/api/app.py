import json
import logging
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError

from iris_agent.api.report_schemas import (
    ApplySuggestionRequest,
    GenerateReportRequest,
    ReportChatRequest,
    RestoreReportRequest,
    ReviseReportRequest,
    SaveReportRequest,
)
from iris_agent.api.schemas import ChatRequest, CreateSessionRequest
from iris_agent.api.aihot_daily_api import router as aihot_daily_router
from iris_agent.api.world_news_api import router as world_news_router
from iris_agent.api.tech_news_api import router as tech_news_router
from iris_agent.api.settings_api import register_settings_routes
from iris_agent.api.skills_api import register_skills_routes
from iris_agent.api.documents_api import register_documents_routes
from iris_agent.api.mcp_api import register_mcp_routes
from iris_agent.api.uml_api import register_uml_routes
from iris_agent.core.agent import AgentService
from iris_agent.core.errors import IrisError, SessionNotFoundError
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.documents.errors import (
    DocumentDraftNotFoundError,
    DocumentError,
    DocumentGenerationError,
    DocumentNotFoundError,
    DocumentRevisionConflictError,
    DocumentStorageError,
    DocumentValidationError,
)
from iris_agent.documents.service import DocumentService
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.reports.errors import (
    ReportAttachmentError,
    ReportAttachmentExtractError,
    ReportAttachmentNotFoundError,
    ReportAttachmentOcrUnavailableError,
    ReportAttachmentStorageError,
    ReportGenerationError,
    ReportNotFoundError,
    ReportSuggestionNotFoundError,
    ReportStorageError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.models import DailyReport, ReportVersion
from iris_agent.reports.attachments import AttachmentRepository, ReportAttachment
from iris_agent.reports.chat import DailyReportChatService, ReportSuggestion
from iris_agent.reports.extraction import LocalAttachmentExtractor
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
        "revision": report.revision,
        "current": _version_data(report.current),
        "versions": [_version_data(item, include_sections=False) for item in report.versions],
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "attachments": [_attachment_data(item) for item in report.attachments],
    }


def _attachment_data(attachment: ReportAttachment) -> dict:
    data = {
        "id": attachment.id,
        "original_name": attachment.original_name,
        "media_type": attachment.media_type,
        "size_bytes": attachment.size_bytes,
        "preserve": attachment.preserve,
        "status": attachment.status,
        "created_at": attachment.created_at,
        "extraction_status": attachment.extraction_status,
    }
    if attachment.extraction_message is not None:
        data["extraction_message"] = attachment.extraction_message
    return data


def _suggestion_data(suggestion: ReportSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "reply": suggestion.reply,
        "sections": suggestion.sections.to_dict(),
        "attachment_ids": list(suggestion.attachment_ids),
        "applied": suggestion.applied,
    }


def _report_summary(report: DailyReport) -> dict:
    completed = report.current.sections.completed
    return {
        "date": report.date,
        "summary": completed[0] if completed else "暂无内容",
        "current_version": report.current_version,
        "revision": report.revision,
        "updated_at": report.updated_at,
    }


def create_app(
    service: AgentService,
    sessions: SessionRepository,
    reports: DailyReportService | None = None,
    attachments: AttachmentRepository | None = None,
    extractor: LocalAttachmentExtractor | None = None,
    skills: SkillCenterService | None = None,
    documents: DocumentService | None = None,
    mcp: McpCenterService | None = None,
) -> FastAPI:
    app = FastAPI(title="Iris Agent API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    # AI HOT 每日资讯日报（独立于工作日报助手）
    app.include_router(aihot_daily_router)
    # 世界时政热点
    app.include_router(world_news_router)
    # 计算机行业新闻
    app.include_router(tech_news_router)
    # AI 配置设置（API Key 等，读写 .env 并动态生效）
    register_settings_routes(app, service)
    # UML 流程图生成（复用现有 LLM provider）
    register_uml_routes(app, service)
    # Skills 中心（可选注入；不注入则不注册路由，保持既有测试兼容）
    if skills is not None:
        register_skills_routes(app, skills)
    if documents is not None:
        register_documents_routes(app, documents)
    if mcp is not None:
        register_mcp_routes(app, mcp)

    @app.exception_handler(IrisError)
    async def iris_error_handler(_, exc: IrisError):
        if isinstance(exc, (SessionNotFoundError, ReportNotFoundError, ReportAttachmentNotFoundError, ReportSuggestionNotFoundError, DocumentNotFoundError, DocumentDraftNotFoundError)):
            code = 404
        elif isinstance(exc, (ReportVersionConflictError, DocumentRevisionConflictError)):
            code = 409
        elif isinstance(exc, (ReportValidationError, ReportAttachmentError, DocumentValidationError)):
            code = 422
        elif isinstance(exc, (ReportGenerationError, DocumentGenerationError)) and exc.code in {"report_model_output_invalid", "document_model_output_invalid"}:
            code = 422
        elif isinstance(exc, (ReportGenerationError, ReportStorageError, ReportAttachmentStorageError, DocumentStorageError)):
            code = 500
        elif isinstance(exc, DocumentError):
            code = 422
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
        chat = DailyReportChatService(reports.provider, reports.repository)
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
                    request.write_revision,
                )
            )

        @app.post("/api/reports/{report_date}/workspace")
        def ensure_report_workspace(report_date: str):
            return _report_data(reports.ensure_workspace(report_date))

        @app.get("/api/reports/{report_date}")
        def get_report(report_date: str):
            return _report_data(reports.get_report(report_date))

        @app.get("/api/reports/{report_date}/versions/{version}")
        def get_report_version(report_date: str, version: int):
            return _version_data(reports.get_version(report_date, version))

        @app.put("/api/reports/{report_date}")
        def save_report(report_date: str, request: SaveReportRequest):
            return _report_data(
                reports.save_manual(report_date, request.sections.to_model(), request.write_revision)
            )

        @app.post("/api/reports/{report_date}/revise")
        def revise_report(report_date: str, request: ReviseReportRequest):
            return _report_data(
                reports.revise(report_date, request.instruction, request.write_revision)
            )

        @app.post("/api/reports/{report_date}/versions/{version}/restore")
        def restore_report(report_date: str, version: int, request: RestoreReportRequest):
            return _report_data(
                reports.restore(report_date, version, request.write_revision)
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

        if attachments is not None:
            @app.post("/api/reports/{report_date}/attachments", status_code=status.HTTP_201_CREATED)
            async def upload_attachments(
                report_date: str,
                files: list[UploadFile] = File(...),
                preserve: bool = Form(False),
            ):
                report = reports.get_report(report_date)
                saved: list[ReportAttachment] = []
                try:
                    for file in files:
                        attachment = attachments.save(
                            report_date,
                            file.filename or "upload",
                            await file.read(),
                            file.content_type or "application/octet-stream",
                            preserve,
                        )
                        saved.append(attachment)
                        if extractor is not None:
                            handle = attachments.path_for(attachment.id)
                            try:
                                extracted = extractor.extract(handle)
                            except ReportAttachmentOcrUnavailableError:
                                attachment = attachments.set_extraction_result(
                                    attachment.id,
                                    extraction_status="unavailable",
                                    extraction_message="本机 OCR 未配置",
                                )
                            except ReportAttachmentExtractError:
                                attachment = attachments.set_extraction_result(
                                    attachment.id,
                                    extraction_status="failed",
                                    extraction_message="无法提取日报附件文本",
                                )
                            else:
                                attachment = attachments.set_extraction_result(
                                    attachment.id,
                                    extraction_status="ready",
                                    extracted_text=extracted.text,
                                )
                            finally:
                                handle.close()
                            saved[-1] = attachment
                    report = reports.update_attachments(
                        report_date,
                        [*report.attachments, *saved],
                        expected_revision=report.revision,
                    )
                except Exception:
                    attachments.cleanup([item.id for item in saved])
                    raise
                return {
                    "attachments": [_attachment_data(item) for item in saved],
                    "report": _report_data(report),
                }

            @app.get("/api/reports/{report_date}/attachments")
            def list_attachments(report_date: str):
                report = reports.get_report(report_date)
                return {"attachments": [_attachment_data(item) for item in report.attachments]}

            @app.delete("/api/reports/{report_date}/attachments/{attachment_id}")
            def delete_attachment(report_date: str, attachment_id: str):
                report = reports.get_report(report_date)
                attachment = next((item for item in report.attachments if item.id == attachment_id), None)
                if attachment is None:
                    raise ReportAttachmentNotFoundError("日报附件不存在")
                updated = reports.update_attachments(
                    report_date,
                    [item for item in report.attachments if item.id != attachment_id],
                    expected_revision=report.revision,
                )
                attachments.delete(attachment_id)
                return {"report": _report_data(updated)}

            @app.post("/api/reports/{report_date}/chat")
            def report_chat(report_date: str, request: ReportChatRequest):
                result = chat.chat(
                    report_date, request.message, request.attachment_ids, request.write_revision
                )
                return {"reply": result.reply, "suggestion": _suggestion_data(result.suggestion)}

            @app.post("/api/reports/{report_date}/suggestions/{suggestion_id}/apply")
            def apply_suggestion(report_date: str, suggestion_id: str, request: ApplySuggestionRequest):
                return _report_data(chat.apply_suggestion(report_date, suggestion_id, request.write_revision))

    return app
