from __future__ import annotations

import json

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.reports.attachments import AttachmentRepository
from iris_agent.reports.extraction import LocalAttachmentExtractor
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


def report_sections(completed: str = "API report") -> dict[str, list[str]]:
    return {
        "completed": [completed], "in_progress": [], "problems": [],
        "next_day": [], "assistance": [],
    }


class FakeProvider:
    def __init__(self) -> None:
        self.content = json.dumps(report_sections(), ensure_ascii=False)

    def complete(self, _messages, tools) -> ProviderResponse:
        return ProviderResponse(content=self.content)


def make_client(tmp_path, extractor: LocalAttachmentExtractor | None = None):
    provider = FakeProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    reports = DailyReportService(provider, sessions, JsonDailyReportRepository(tmp_path / "reports"))
    attachments = AttachmentRepository(tmp_path / "attachments", 1_000, 5_000, 3)
    agent = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    return TestClient(create_app(agent, sessions, reports, attachments, extractor=extractor)), provider


def generate(client: TestClient) -> None:
    response = client.post("/api/reports/generate", json={
        "date": "2026-08-07", "notes": "notes", "include_chat": False,
        "session_id": None, "expected_version": None,
    })
    assert response.status_code == 201


def test_upload_list_and_delete_attachments_without_exposing_server_paths(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    generate(client)

    uploaded = client.post(
        "/api/reports/2026-08-07/attachments",
        files=[("files", ("notes.txt", b"completed API", "text/plain"))],
        data={"preserve": "true"},
    )

    assert uploaded.status_code == 201
    item = uploaded.json()["attachments"][0]
    assert item["original_name"] == "notes.txt"
    assert item["preserve"] is True
    assert "path" not in item
    assert str(tmp_path) not in json.dumps(uploaded.json())
    assert client.get("/api/reports/2026-08-07/attachments").json()["attachments"] == [item]

    deleted = client.delete(f"/api/reports/2026-08-07/attachments/{item['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["report"]["attachments"] == []
    assert client.get("/api/reports/2026-08-07/attachments").json()["attachments"] == []


def test_attachment_mutations_advance_report_revision_and_return_the_updated_report(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    generate(client)
    initial = client.get("/api/reports/2026-08-07").json()

    uploaded = client.post(
        "/api/reports/2026-08-07/attachments",
        files=[("files", ("notes.txt", b"completed API", "text/plain"))],
        data={"preserve": "false"},
    )

    assert uploaded.status_code == 201
    after_upload = uploaded.json()["report"]
    assert after_upload["revision"] == initial["revision"] + 1
    stale_save = client.put(
        "/api/reports/2026-08-07",
        json={"sections": report_sections("stale"), "expected_revision": initial["revision"]},
    )
    assert stale_save.status_code == 409

    deleted = client.delete(
        f"/api/reports/2026-08-07/attachments/{uploaded.json()['attachments'][0]['id']}",
    )

    assert deleted.status_code == 200
    assert deleted.json()["report"]["revision"] == after_upload["revision"] + 1
    assert deleted.json()["report"]["attachments"] == []


def test_upload_reports_safe_extraction_status_and_keeps_ocr_unavailable_attachment(tmp_path) -> None:
    client, _ = make_client(tmp_path, extractor=LocalAttachmentExtractor(max_chars=100))
    generate(client)

    uploaded = client.post(
        "/api/reports/2026-08-07/attachments",
        files=[
            ("files", ("notes.txt", "完成接口".encode(), "text/plain")),
            ("files", ("picture.png", b"not-an-image", "image/png")),
            ("files", ("broken.pdf", b"not-a-pdf", "application/pdf")),
        ],
        data={"preserve": "true"},
    )

    assert uploaded.status_code == 201
    items = uploaded.json()["attachments"]
    assert [item["extraction_status"] for item in items] == ["ready", "unavailable", "failed"]
    assert "extraction_message" not in items[0]
    assert items[1]["extraction_message"] == "本机 OCR 未配置"
    assert items[2]["extraction_message"] == "无法提取日报附件文本"
    response_text = json.dumps(uploaded.json(), ensure_ascii=False)
    assert "extracted_text" not in response_text
    assert "完成接口" not in response_text
    assert "path" not in response_text
    assert str(tmp_path) not in response_text
    assert client.get("/api/reports/2026-08-07/attachments").json()["attachments"] == items


def test_chat_and_apply_suggestion_are_explicit_and_versioned(tmp_path) -> None:
    client, provider = make_client(tmp_path)
    generate(client)
    upload_response = client.post(
        "/api/reports/2026-08-07/attachments",
        files=[("files", ("notes.txt", b"completed API", "text/plain"))],
        data={"preserve": "false"},
    ).json()
    upload = upload_response["attachments"][0]
    provider.content = json.dumps({
        "reply": "Use the attachment.", "sections": report_sections("Applied"),
        "attachment_ids": [upload["id"]],
    })

    chat = client.post("/api/reports/2026-08-07/chat", json={
        "message": "Make a report", "attachment_ids": [upload["id"]],
        "expected_revision": upload_response["report"]["revision"],
    })

    assert chat.status_code == 200
    assert chat.json()["suggestion"]["attachment_ids"] == [upload["id"]]
    applied = client.post(
        f"/api/reports/2026-08-07/suggestions/{chat.json()['suggestion']['id']}/apply",
        json={"expected_revision": upload_response["report"]["revision"]},
    )
    assert applied.status_code == 200
    assert applied.json()["current_version"] == 2


def test_attachment_errors_are_stable_and_safe(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    generate(client)

    invalid = client.post(
        "/api/reports/2026-08-07/attachments",
        files=[("files", ("danger.exe", b"x", "application/octet-stream"))],
        data={"preserve": "false"},
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "report_attachment_invalid_type"
    assert str(tmp_path) not in json.dumps(invalid.json())
