from __future__ import annotations

import json
from uuid import uuid4

import pytest

from iris_agent.core.models import Message, ProviderResponse
from iris_agent.reports.attachments import ReportAttachment
from iris_agent.reports.errors import ReportGenerationError, ReportVersionConflictError
from iris_agent.reports.models import ReportSections
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.reports.chat import DailyReportChatService
from iris_agent.sessions.json_store import JsonSessionRepository


def sections(completed: list[str] | None = None) -> dict[str, list[str]]:
    return {
        "completed": completed or ["原始内容"],
        "in_progress": [],
        "problems": [],
        "next_day": [],
        "assistance": [],
    }


class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[tuple[list[Message], list[dict]]] = []

    def complete(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        self.calls.append((messages, tools))
        return ProviderResponse(content=self.content)


def make_services(tmp_path, content: str):
    provider = FakeProvider(json.dumps(sections(), ensure_ascii=False))
    repository = JsonDailyReportRepository(tmp_path / "reports")
    reports = DailyReportService(provider, JsonSessionRepository(tmp_path / "sessions"), repository)
    report = reports.generate("2026-08-05", "记录", None, include_chat=False)
    provider.content = content
    return provider, repository, report, DailyReportChatService(provider, repository)


def valid_reply(**overrides) -> str:
    result = {
        "reply": "已整理出建议。",
        "sections": sections(["应用后的内容"]),
        "attachment_ids": [],
    }
    result.update(overrides)
    return json.dumps(result, ensure_ascii=False)


def test_chat_includes_selected_extracted_attachment_text_and_disables_tools(tmp_path) -> None:
    provider, repository, report, chat = make_services(tmp_path, valid_reply())
    attachment = ReportAttachment(
        id=str(uuid4()), original_name="notes.txt", media_type="text/plain", size_bytes=4,
        preserve=True, status="preserved", extracted_text="附件中的关键结论",
    )
    report.attachments.append(attachment)
    report.revision += 1
    repository.save(report, expected_revision=report.revision - 1)

    suggestion = chat.chat("2026-08-05", "请据此优化", [attachment.id], report.revision)

    payload = json.loads(provider.calls[-1][0][-1].content)
    assert payload["attachments"] == [{"id": attachment.id, "name": "notes.txt", "text": "附件中的关键结论"}]
    assert provider.calls[-1][1] == []
    assert suggestion.reply == "已整理出建议。"
    assert suggestion.sections.completed == ("应用后的内容",)
    assert repository.get("2026-08-05").current_version == report.current_version


def test_invalid_chat_model_output_does_not_save_a_suggestion_or_modify_report(tmp_path) -> None:
    _, repository, report, chat = make_services(tmp_path, "not json")

    with pytest.raises(ReportGenerationError) as caught:
        chat.chat("2026-08-05", "请优化", [], report.current_version)

    assert caught.value.code == "report_model_output_invalid"
    assert repository.get("2026-08-05").current_version == report.current_version
    with pytest.raises(Exception) as missing:
        chat.apply_suggestion("2026-08-05", "missing", report.current_version)
    assert getattr(missing.value, "code", None) == "report_suggestion_not_found"


def test_apply_suggestion_checks_version_and_can_only_be_applied_once(tmp_path) -> None:
    _, repository, report, chat = make_services(tmp_path, valid_reply())
    suggestion = chat.chat("2026-08-05", "请优化", [], report.current_version)

    with pytest.raises(ReportVersionConflictError):
        chat.apply_suggestion("2026-08-05", suggestion.id, expected_version=0)
    applied = chat.apply_suggestion("2026-08-05", suggestion.id, expected_version=report.current_version)

    assert applied.current_version == report.current_version + 1
    assert applied.current.kind == "ai_revision"
    assert applied.current.sections.completed == ("应用后的内容",)
    with pytest.raises(Exception) as duplicate:
        chat.apply_suggestion("2026-08-05", suggestion.id, expected_version=applied.current_version)
    assert getattr(duplicate.value, "code", None) == "report_suggestion_already_applied"
    assert repository.get("2026-08-05").current_version == applied.current_version


def test_apply_rejects_a_suggestion_created_before_a_report_restore(tmp_path) -> None:
    provider = FakeProvider(json.dumps(sections(), ensure_ascii=False))
    repository = JsonDailyReportRepository(tmp_path / "reports")
    reports = DailyReportService(provider, JsonSessionRepository(tmp_path / "sessions"), repository)
    first = reports.generate("2026-08-05", "记录", None, include_chat=False)
    second = reports.save_manual(
        "2026-08-05", ReportSections(completed=("后来的内容",)), first.revision,
    )
    provider.content = valid_reply()
    chat = DailyReportChatService(provider, repository)
    suggestion = chat.chat("2026-08-05", "请优化", [], second.revision)
    restored = reports.restore("2026-08-05", 1, second.revision)

    with pytest.raises(ReportVersionConflictError):
        chat.apply_suggestion("2026-08-05", suggestion.id, restored.revision)

    assert repository.get("2026-08-05").current_version == 1
