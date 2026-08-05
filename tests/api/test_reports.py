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


def sections(completed: str = "完成日报接口") -> dict[str, list[str]]:
    return {
        "completed": [completed],
        "in_progress": [],
        "problems": [],
        "next_day": ["接入前端"],
        "assistance": [],
    }


class FakeProvider:
    def __init__(self):
        self.content = json.dumps(sections(), ensure_ascii=False)

    def complete(self, _messages, _tools):
        return ProviderResponse(content=self.content)


def make_client(tmp_path):
    provider = FakeProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    reports = DailyReportService(
        provider,
        sessions,
        JsonDailyReportRepository(tmp_path / "reports"),
        clock=lambda: 100.0,
    )
    return TestClient(create_app(agent, sessions, reports)), provider


def generate(client: TestClient):
    return client.post(
        "/api/reports/generate",
        json={
            "date": "2026-08-05",
            "notes": "完成接口开发",
            "include_chat": False,
            "session_id": None,
            "expected_version": None,
        },
    )


def test_generate_list_get_and_download_report(tmp_path) -> None:
    client, _ = make_client(tmp_path)

    created = generate(client)

    assert created.status_code == 201
    assert created.json()["current"]["kind"] == "generated"
    assert created.json()["current"]["sections"]["completed"] == ["完成日报接口"]
    listing = client.get("/api/reports")
    assert listing.json()["reports"][0]["date"] == "2026-08-05"
    fetched = client.get("/api/reports/2026-08-05")
    assert fetched.json()["current_version"] == 1
    version = client.get("/api/reports/2026-08-05/versions/1")
    assert version.json()["number"] == 1

    download = client.get("/api/reports/2026-08-05/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")
    assert "2026-08-05" in download.headers["content-disposition"]
    assert "## 今日完成" in download.text


def test_manual_save_revision_and_restore(tmp_path) -> None:
    client, provider = make_client(tmp_path)
    first = generate(client).json()

    manual = client.put(
        "/api/reports/2026-08-05",
        json={"sections": sections("手动修改"), "expected_version": first["current_version"]},
    )
    assert manual.status_code == 200
    assert manual.json()["current"]["kind"] == "manual"

    provider.content = json.dumps(sections("AI 修改"), ensure_ascii=False)
    revised = client.post(
        "/api/reports/2026-08-05/revise",
        json={"instruction": "突出成果", "expected_version": manual.json()["current_version"]},
    )
    assert revised.json()["current"]["kind"] == "ai_revision"

    restored = client.post(
        "/api/reports/2026-08-05/versions/1/restore",
        json={"expected_version": revised.json()["current_version"]},
    )
    assert restored.json()["current"]["kind"] == "restored"
    assert restored.json()["current"]["sections"]["completed"] == ["完成日报接口"]


def test_stale_write_returns_stable_conflict(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    generate(client)

    response = client.put(
        "/api/reports/2026-08-05",
        json={"sections": sections("过期修改"), "expected_version": 0},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "report_version_conflict"


def test_unknown_and_invalid_report_dates_have_stable_errors(tmp_path) -> None:
    client, _ = make_client(tmp_path)

    missing = client.get("/api/reports/2026-08-05")
    invalid = client.get("/api/reports/not-a-date")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "report_not_found"
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "report_invalid_date"


def test_invalid_model_output_returns_422_without_creating_report(tmp_path) -> None:
    client, provider = make_client(tmp_path)
    provider.content = "not json"

    response = generate(client)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "report_model_output_invalid"
    assert client.get("/api/reports/2026-08-05").status_code == 404


def test_report_input_errors_keep_report_specific_codes(tmp_path) -> None:
    client, _ = make_client(tmp_path)

    too_long = client.post(
        "/api/reports/generate",
        json={
            "date": "2026-08-05",
            "notes": "x" * 50_001,
            "include_chat": False,
            "session_id": None,
        },
    )
    missing_session = client.post(
        "/api/reports/generate",
        json={
            "date": "2026-08-05",
            "notes": "记录",
            "include_chat": True,
            "session_id": None,
        },
    )

    assert too_long.status_code == 422
    assert too_long.json()["detail"]["code"] == "report_input_too_long"
    assert missing_session.status_code == 422
    assert missing_session.json()["detail"]["code"] == "report_session_required"


def test_generate_with_current_chat_session(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    session = client.post("/api/sessions", json={"name": "日报来源"}).json()
    client.post("/api/chat/stream", json={"session_id": session["id"], "message": "完成会话导入"})

    response = client.post(
        "/api/reports/generate",
        json={
            "date": "2026-08-05",
            "notes": "手动记录",
            "include_chat": True,
            "session_id": session["id"],
            "expected_version": None,
        },
    )

    assert response.status_code == 201
    assert response.json()["source_session_id"] == session["id"]
