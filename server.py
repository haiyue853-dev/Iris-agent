"""Iris Agent FastAPI compatibility entry point."""

from dotenv import load_dotenv

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationScheduler
from iris_agent.attachments.scheduler import AttachmentCleanupScheduler
from iris_agent.bootstrap import build_application
from iris_agent.curator.scheduler import CuratorScheduler
from iris_agent.gateway.napcat import start_napcat_if_enabled
from iris_agent.logging_setup import configure_logging
from iris_agent.personal_assistant.scheduler import PersonalReminderScheduler
from iris_agent.reports.extraction import LocalAttachmentExtractor
from iris_agent.startup_report import report_startup

load_dotenv()
# 必须在 build_application 之前：启动阶段的失败（配置错误、NapCat 拉不起来）也要落盘。
log_path = configure_logging()
application = build_application()
# 打出生效的配置，并提示「磁盘上有改动但不在本进程里」——今天在这上面栽过三次。
for line in report_startup(application.settings, log_path=log_path):
    print(line, flush=True)
app = create_app(
    application.agent, application.sessions, application.reports, application.attachments,
    LocalAttachmentExtractor(application.settings.reports.max_attachment_text_chars),
    skills=application.skills,
    hot_radar=application.hot_radar,
    automation=application.automation,
    notifications=application.notifications,
    task_center=application.task_center,
    task_queue=application.task_queue,
    delegation=application.subagent.delegation,
    memory=application.memory,
    search=application.session_search,
    profile=application.profile,
    knowledge=application.knowledge,
    curator=application.curator,
    mcp=application.mcp,
    mcp_tools=application.mcp_tools,
    gateway=application.gateway,
    qq_adapter=application.qq_adapter,
    napcat=application.napcat,
    wecom_adapter=application.wecom_adapter,
    wecom_aibot=application.wecom_aibot,
    qq_ws_path=application.settings.gateway.qq.path,
    wecom_callback_path=application.settings.gateway.wecom.callback_path,
    chat_attachments=application.chat_attachments,
    settings_profiles=application.settings_profiles,
    tts=application.tts,
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
personal_reminder_scheduler = (
    PersonalReminderScheduler(
        application.personal_assistant,
        lambda platform, user_id, text: bool(
            application.wecom_aibot.send_text(user_id, text)
            if platform == "wecom" and application.wecom_aibot is not None
            else application.qq_adapter and application.qq_adapter.push_text(user_id, text)
        ),
    )
    if application.personal_assistant is not None
    and (application.qq_adapter is not None or application.wecom_aibot is not None)
    else None
)


@app.on_event("startup")
def start_automation_scheduler() -> None:
    scheduler.start()
    attachment_cleanup_scheduler.start()
    application.task_queue.start()
    if curator_scheduler is not None:
        curator_scheduler.start()
    if application.wecom_aibot is not None:
        application.wecom_aibot.start()
    if personal_reminder_scheduler is not None:
        personal_reminder_scheduler.start()
    start_napcat_if_enabled(
        application.napcat,
        enabled=application.settings.gateway.napcat_auto_start,
    )


@app.on_event("shutdown")
def stop_automation_scheduler() -> None:
    application.task_queue.stop()
    attachment_cleanup_scheduler.stop()
    scheduler.stop()
    if curator_scheduler is not None:
        curator_scheduler.stop()
    if personal_reminder_scheduler is not None:
        personal_reminder_scheduler.stop()
    application.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
