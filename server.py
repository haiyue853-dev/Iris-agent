"""Iris Agent FastAPI compatibility entry point."""

from dotenv import load_dotenv

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationScheduler
from iris_agent.attachments.scheduler import AttachmentCleanupScheduler
from iris_agent.bootstrap import build_application
from iris_agent.curator.scheduler import CuratorScheduler
from iris_agent.reports.extraction import LocalAttachmentExtractor

load_dotenv()
application = build_application()
app = create_app(
    application.agent, application.sessions, application.reports, application.attachments,
    LocalAttachmentExtractor(application.settings.reports.max_attachment_text_chars),
    skills=application.skills,
    hot_radar=application.hot_radar,
    automation=application.automation,
    notifications=application.notifications,
    task_center=application.task_center,
    task_queue=application.task_queue,
    memory=application.memory,
    search=application.session_search,
    profile=application.profile,
    knowledge=application.knowledge,
    curator=application.curator,
    mcp=application.mcp,
    mcp_tools=application.mcp_tools,
    gateway=application.gateway,
    qq_adapter=application.qq_adapter,
    wecom_adapter=application.wecom_adapter,
    qq_ws_path=application.settings.gateway.qq.path,
    wecom_callback_path=application.settings.gateway.wecom.callback_path,
    chat_attachments=application.chat_attachments,
)
scheduler = AutomationScheduler(application.automation)
attachment_cleanup_scheduler = AttachmentCleanupScheduler(
    application.chat_attachments,
    interval_seconds=max(60, min(application.settings.attachments.temporary_ttl_seconds, 3600)),
)
curator_scheduler = (
    CuratorScheduler(application.curator, application.notifications, application.settings.curator.schedule)
    if application.settings.curator.auto_run
    else None
)


@app.on_event("startup")
def start_automation_scheduler() -> None:
    scheduler.start()
    attachment_cleanup_scheduler.start()
    application.task_queue.start()
    if curator_scheduler is not None:
        curator_scheduler.start()


@app.on_event("shutdown")
def stop_automation_scheduler() -> None:
    application.task_queue.stop()
    attachment_cleanup_scheduler.stop()
    scheduler.stop()
    if curator_scheduler is not None:
        curator_scheduler.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
