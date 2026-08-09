from __future__ import annotations

import json

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class FakeProvider:
    def complete(self, _messages, _tools):
        return ProviderResponse(
            content=json.dumps(
                {
                    "completed": [],
                    "in_progress": [],
                    "problems": [],
                    "next_day": [],
                    "assistance": [],
                }
            )
        )


def make_client(tmp_path) -> TestClient:
    provider = FakeProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    reports = DailyReportService(
        provider,
        sessions,
        JsonDailyReportRepository(tmp_path / "reports"),
        clock=lambda: 100.0,
    )
    return TestClient(create_app(agent, sessions, reports))


def test_workspace_creates_and_reuses_blank_report(tmp_path) -> None:
    client = make_client(tmp_path)
    empty_sections = {
        "completed": [],
        "in_progress": [],
        "problems": [],
        "next_day": [],
        "assistance": [],
    }

    created = client.post("/api/reports/2026-08-09/workspace")

    assert created.status_code == 200
    first = created.json()
    assert first["date"] == "2026-08-09"
    assert first["source_notes"] == ""
    assert first["source_session_id"] is None
    assert first["current_version"] == 1
    assert first["current"]["number"] == 1
    assert first["current"]["sections"] == empty_sections
    assert first["versions"][0]["number"] == 1
    assert first["created_at"] == first["updated_at"] == first["current"]["created_at"] == 100.0

    reused = client.post("/api/reports/2026-08-09/workspace")

    assert reused.status_code == 200
    assert reused.json()["current_version"] == 1
    assert reused.json() == first

