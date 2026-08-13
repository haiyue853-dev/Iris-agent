import json
import logging
from time import monotonic
import threading
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

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
from iris_agent.api.mcp_api import register_mcp_routes
from iris_agent.api.hot_radar_api import register_hot_radar_routes
from iris_agent.api.uml_api import register_uml_routes
from iris_agent.core.agent import AgentService
from iris_agent.core.errors import IrisError, SessionNotFoundError
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.hot_radar.service import HotRadarService
from iris_agent.automation.service import AutomationService
from iris_agent.api.automation_api import register_automation_routes
from iris_agent.api.notifications_api import register_notification_routes
from iris_agent.notifications.service import NotificationService
from iris_agent.task_center.service import TaskCenterService
from iris_agent.api.tasks_api import register_task_routes
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


class ToolApprovalRequest(BaseModel):
    approved: bool


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
    mcp: McpCenterService | None = None,
    mcp_tools=None,
    hot_radar: HotRadarService | None = None,
    automation: AutomationService | None = None,
    notifications: NotificationService | None = None,
    task_center: TaskCenterService | None = None,
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
    if mcp is not None:
        register_mcp_routes(app, mcp, mcp_tools)
    if hot_radar is not None:
        register_hot_radar_routes(app, hot_radar)
    if automation is not None:
        register_automation_routes(app, automation)
    if notifications is not None:
        register_notification_routes(app, notifications)
    if task_center is not None:
        register_task_routes(app, task_center)

    approval_tasks: dict[tuple[str, str], str] = {}
    approval_tool_names: dict[tuple[str, str], str] = {}
    tool_started_at: dict[tuple[str, str], float] = {}
    processing_approvals: set[tuple[str, str]] = set()
    approval_lock = threading.Lock()

    def clear_approval(session_id: str, call_id: str) -> None:
        with approval_lock:
            approval_tasks.pop((session_id, call_id), None)
            approval_tool_names.pop((session_id, call_id), None)
            tool_started_at.pop((session_id, call_id), None)
            processing_approvals.discard((session_id, call_id))
        service.cancel_tool_approval(session_id, call_id)

    def clear_task_approvals(task_id: str) -> None:
        with approval_lock:
            keys = [key for key, value in approval_tasks.items() if value == task_id]
            for session_id, call_id in keys:
                approval_tasks.pop((session_id, call_id), None)
                approval_tool_names.pop((session_id, call_id), None)
                tool_started_at.pop((session_id, call_id), None)
                processing_approvals.discard((session_id, call_id))
                service.cancel_tool_approval(session_id, call_id)

    @app.exception_handler(IrisError)
    async def iris_error_handler(_, exc: IrisError):
        if isinstance(exc, (SessionNotFoundError, ReportNotFoundError, ReportAttachmentNotFoundError, ReportSuggestionNotFoundError)):
            code = 404
        elif isinstance(exc, ReportVersionConflictError):
            code = 409
        elif isinstance(exc, (ReportValidationError, ReportAttachmentError)):
            code = 422
        elif isinstance(exc, ReportGenerationError) and exc.code == "report_model_output_invalid":
            code = 422
        elif isinstance(exc, (ReportGenerationError, ReportStorageError, ReportAttachmentStorageError)):
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
            task_id: str | None = None
            terminal = False
            try:
                if task_center is not None:
                    task_id = task_center.create_task(request.session_id, request.message).id
                    yield json.dumps({"type": "task_started", "data": {"task_id": task_id}}, ensure_ascii=False) + "\n"
                for event in service.run(request.session_id, request.message):
                    if task_id is not None:
                        if event.type == "tool_started":
                            task_center.tool_started(task_id, str(event.data["name"]))
                            with approval_lock:
                                tool_started_at[(request.session_id, str(event.data["call_id"]))] = monotonic()
                        elif event.type == "tool_approval_requested":
                            call_id = str(event.data["call_id"])
                            tool_name = str(event.data["name"])
                            task_center.approval_requested(task_id, call_id, tool_name)
                            with approval_lock:
                                approval_tasks[(request.session_id, call_id)] = task_id
                                approval_tool_names[(request.session_id, call_id)] = tool_name
                        elif event.type == "tool_finished":
                            with approval_lock:
                                started_at = tool_started_at.pop((request.session_id, str(event.data["call_id"])), None)
                            duration_ms = None if started_at is None else int((monotonic() - started_at) * 1000)
                            task_center.tool_finished(task_id, str(event.data["name"]), duration_ms, succeeded=bool(event.data.get("ok")))
                        elif event.type == "text_delta":
                            task_center.touch(task_id)
                        elif event.type == "message_completed":
                            task_center.complete(task_id)
                            terminal = True
                        elif event.type == "error":
                            task_center.fail(task_id)
                            terminal = True
                    yield json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                if task_id is not None and not terminal and task_center.get_task(task_id).status == "running":
                    task_center.fail(task_id)
                    terminal = True
            except GeneratorExit:
                if task_id is not None and not terminal:
                    task_center.stop(task_id)
                    clear_task_approvals(task_id)
                raise
            except IrisError as exc:
                if task_id is not None and not terminal:
                    task_center.fail(task_id)
                    clear_task_approvals(task_id)
                yield json.dumps({"type": "error", "data": {"code": exc.code, "message": exc.safe_message}}, ensure_ascii=False) + "\n"
            except Exception:
                if task_id is not None and not terminal:
                    task_center.fail(task_id)
                    clear_task_approvals(task_id)
                logger.exception("流式对话发生未处理异常")
                yield json.dumps({"type": "error", "data": {"code": "internal_error", "message": "服务内部错误"}}, ensure_ascii=False) + "\n"

        return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/sessions/{session_id}/tool-approvals/{call_id}")
    def resolve_tool_approval(session_id: str, call_id: str, request: ToolApprovalRequest):
        sessions.get(session_id)

        def generate():
            with approval_lock:
                task_id = approval_tasks.pop((session_id, call_id), None) if task_center is not None else None
                tool_name = approval_tool_names.pop((session_id, call_id), None)
                already_processing = (session_id, call_id) in processing_approvals
                if task_id is not None:
                    processing_approvals.add((session_id, call_id))
            terminal = False
            try:
                if task_center is not None and task_id is None:
                    yield json.dumps({"type": "error", "data": {"code": "tool_approval_not_found", "message": "待确认的工具调用不存在或已处理"}}, ensure_ascii=False) + "\n"
                    return
                if task_id is not None:
                    task_center.record_approval(task_id, call_id, tool_name, request.approved)
                    with approval_lock:
                        tool_started_at.setdefault((session_id, call_id), monotonic())
                for event in service.resolve_tool_approval(session_id, call_id, request.approved):
                    if task_id is not None:
                        if event.type == "tool_finished":
                            with approval_lock:
                                started_at = tool_started_at.pop((session_id, call_id), None)
                            duration_ms = None if started_at is None else int((monotonic() - started_at) * 1000)
                            task_center.tool_finished(
                                task_id,
                                str(event.data["name"]),
                                call_id=call_id,
                                duration_ms=duration_ms,
                                succeeded=bool(event.data.get("ok")),
                            )
                        elif event.type == "tool_started":
                            task_center.tool_started(task_id, str(event.data["name"]))
                            with approval_lock:
                                tool_started_at[(session_id, str(event.data["call_id"]))] = monotonic()
                        elif event.type == "text_delta":
                            task_center.touch(task_id)
                        elif event.type == "tool_approval_requested":
                            next_call_id = str(event.data["call_id"])
                            tool_name = str(event.data["name"])
                            task_center.approval_requested(task_id, next_call_id, tool_name)
                            with approval_lock:
                                approval_tasks[(session_id, next_call_id)] = task_id
                                approval_tool_names[(session_id, next_call_id)] = tool_name
                        elif event.type == "message_completed":
                            task_center.complete(task_id)
                            terminal = True
                        elif event.type == "error":
                            task_center.fail(task_id)
                            terminal = True
                    yield json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                if task_id is not None and not terminal and task_center.get_task(task_id).status == "running":
                    task_center.fail(task_id)
                    terminal = True
                clear_approval(session_id, call_id)
            except GeneratorExit:
                if task_id is not None and not terminal:
                    task_center.stop(task_id)
                    clear_task_approvals(task_id)
                raise
            except IrisError as exc:
                if task_id is not None and not terminal:
                    task_center.fail(task_id)
                    clear_task_approvals(task_id)
                yield json.dumps({"type": "error", "data": {"code": exc.code, "message": exc.safe_message}}, ensure_ascii=False) + "\n"
            except Exception:
                if task_id is not None and not terminal:
                    task_center.fail(task_id)
                    clear_task_approvals(task_id)
                logger.exception("Tool approval handling failed")
                yield json.dumps({"type": "error", "data": {"code": "internal_error", "message": "Internal server error"}}, ensure_ascii=False) + "\n"
            finally:
                if task_id is not None:
                    clear_approval(session_id, call_id)

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
