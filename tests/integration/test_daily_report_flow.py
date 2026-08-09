from __future__ import annotations

import json
from collections import deque

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def report_sections(completed: str) -> str:
    return json.dumps(
        {
            "completed": [completed],
            "in_progress": [],
            "problems": [],
            "next_day": ["继续完善 Iris Agent"],
            "assistance": [],
        },
        ensure_ascii=False,
    )


class SequencedProvider:
    def __init__(self) -> None:
        self.responses = deque(
            [
                "已记录今天的工作内容",
                report_sections("完成日报完整流程"),
                report_sections("完成日报完整流程并验证关键结果"),
            ]
        )
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return ProviderResponse(content=self.responses.popleft())


def make_application(tmp_path):
    provider = SequencedProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    reports = DailyReportService(
        provider,
        sessions,
        JsonDailyReportRepository(tmp_path / "reports"),
        clock=lambda: 100.0,
    )
    return TestClient(create_app(agent, sessions, reports)), provider


def test_daily_report_flow_from_chat_to_restored_markdown(tmp_path) -> None:
    client, provider = make_application(tmp_path)
    session = client.post("/api/sessions", json={"name": "今日工作"}).json()
    chat = client.post(
        "/api/chat/stream",
        json={"session_id": session["id"], "message": "完成 Iris Agent 日报工作台"},
    )
    assert chat.status_code == 200

    generated_response = client.post(
        "/api/reports/generate",
        json={
            "date": "2026-08-05",
            "notes": "补齐前后端自动化测试",
            "include_chat": True,
            "session_id": session["id"],
            "expected_version": None,
        },
    )
    assert generated_response.status_code == 201
    generated = generated_response.json()
    assert generated["current"]["kind"] == "generated"
    generation_source = provider.calls[1][0][-1].content
    assert "完成 Iris Agent 日报工作台" in generation_source
    assert "补齐前后端自动化测试" in generation_source
    assert provider.calls[1][1] == []

    revised_response = client.post(
        "/api/reports/2026-08-05/revise",
        json={
            "instruction": "突出验证结果",
            "expected_version": generated["current_version"],
        },
    )
    assert revised_response.status_code == 200
    revised = revised_response.json()
    assert revised["current"]["kind"] == "ai_revision"

    restored_response = client.post(
        "/api/reports/2026-08-05/versions/1/restore",
        json={"expected_version": revised["current_version"]},
    )
    assert restored_response.status_code == 200
    restored = restored_response.json()
    assert restored["current_version"] == 1
    assert restored["current"]["kind"] == "generated"
    assert restored["current"]["sections"]["completed"] == ["完成日报完整流程"]
    assert [item["number"] for item in restored["versions"]] == [1, 2]

    markdown = client.get("/api/reports/2026-08-05/download")
    assert markdown.status_code == 200
    assert "## 今日完成" in markdown.text
    assert "- 完成日报完整流程" in markdown.text
