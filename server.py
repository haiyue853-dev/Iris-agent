"""Iris Agent FastAPI compatibility entry point."""

from dotenv import load_dotenv

from iris_agent.api.app import create_app
from iris_agent.automation.service import AutomationScheduler
from iris_agent.bootstrap import build_application
from iris_agent.reports.extraction import LocalAttachmentExtractor

load_dotenv(override=True)
application = build_application()
app = create_app(
    application.agent, application.sessions, application.reports, application.attachments,
    LocalAttachmentExtractor(application.settings.reports.max_attachment_text_chars),
    skills=application.skills,
    hot_radar=application.hot_radar,
    automation=application.automation,
    notifications=application.notifications,
    task_center=application.task_center,
    mcp=application.mcp,
    mcp_tools=application.mcp_tools,
    interview_knowledge=application.interview_knowledge,
    interview_collector=application.interview_collector,
    task_plans=application.task_plans,
    memory=application.memory,
    subagents=application.subagents,
)
scheduler = AutomationScheduler(application.automation)


@app.on_event("startup")
def start_automation_scheduler() -> None:
    scheduler.start()


@app.on_event("shutdown")
def stop_automation_scheduler() -> None:
    scheduler.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
