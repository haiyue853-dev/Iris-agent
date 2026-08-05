from __future__ import annotations

import json

import pytest

from iris_agent.core.models import Message, ProviderResponse
from iris_agent.reports.errors import (
    ReportGenerationError,
    ReportNotFoundError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.json_store import JsonSessionRepository


def valid_sections(**overrides) -> dict[str, list[str]]:
    sections = {
        "completed": ["完成日报服务"],
        "in_progress": [],
        "problems": [],
        "next_day": ["接入 API"],
        "assistance": [],
    }
    sections.update(overrides)
    return sections


class FakeProvider:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content if content is not None else json.dumps(valid_sections(), ensure_ascii=False)
        self.error = error
        self.calls: list[tuple[list[Message], list[dict]]] = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        if self.error is not None:
            raise self.error
        return ProviderResponse(content=self.content)


def make_service(tmp_path, provider: FakeProvider, *, max_input_chars: int = 50_000):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    repository = JsonDailyReportRepository(tmp_path / "reports")
    service = DailyReportService(
        provider,
        sessions,
        repository,
        max_input_chars=max_input_chars,
        clock=lambda: 100.0,
    )
    return service, sessions, repository


def test_generate_uses_manual_notes_and_only_current_chat_text(tmp_path) -> None:
    provider = FakeProvider()
    service, sessions, _ = make_service(tmp_path, provider)
    current = sessions.create("日报来源")
    other = sessions.create("其他会话")
    sessions.append(current.id, Message(role="user", content="完成接口设计"))
    sessions.append(current.id, Message(role="assistant", content="已整理"))
    sessions.append(current.id, Message(role="tool", content="工具秘密"))
    sessions.append(current.id, Message(role="assistant", content="   "))
    sessions.append(other.id, Message(role="user", content="不应导入"))

    report = service.generate(
        "2026-08-05",
        "修复页面布局",
        current.id,
        include_chat=True,
    )

    request_payload = json.loads(provider.calls[0][0][-1].content)
    assert request_payload["manual_notes"] == "修复页面布局"
    assert request_payload["chat"] == [
        {"role": "user", "content": "完成接口设计"},
        {"role": "assistant", "content": "已整理"},
    ]
    assert provider.calls[0][1] == []
    assert report.source_session_id == current.id
    assert [item.content for item in report.source_chat_snapshot] == ["完成接口设计", "已整理"]
    assert report.current.kind == "generated"
    assert report.current_version == 1


def test_generate_without_chat_does_not_require_session(tmp_path) -> None:
    service, _, _ = make_service(tmp_path, FakeProvider())

    report = service.generate("2026-08-05", "仅手动记录", None, include_chat=False)

    assert report.source_session_id is None
    assert report.source_chat_snapshot == ()


def test_generate_requires_session_when_chat_import_enabled(tmp_path) -> None:
    service, _, _ = make_service(tmp_path, FakeProvider())

    with pytest.raises(ReportValidationError) as caught:
        service.generate("2026-08-05", "记录", None, include_chat=True)

    assert caught.value.code == "report_session_required"


def test_generate_rejects_oversized_manual_notes_before_model_call(tmp_path) -> None:
    provider = FakeProvider()
    service, _, _ = make_service(tmp_path, provider, max_input_chars=4)

    with pytest.raises(ReportValidationError) as caught:
        service.generate("2026-08-05", "12345", None, include_chat=False)

    assert caught.value.code == "report_input_too_long"
    assert provider.calls == []


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"completed": []}),
        json.dumps({**valid_sections(), "extra": []}),
        json.dumps(valid_sections(completed="不是数组"), ensure_ascii=False),
        json.dumps(valid_sections(completed=[1]), ensure_ascii=False),
    ],
)
def test_invalid_model_output_fails_without_saving(tmp_path, content) -> None:
    service, _, repository = make_service(tmp_path, FakeProvider(content))

    with pytest.raises(ReportGenerationError) as caught:
        service.generate("2026-08-05", "记录", None, include_chat=False)

    assert caught.value.code == "report_model_output_invalid"
    with pytest.raises(ReportNotFoundError):
        repository.get("2026-08-05")


def test_provider_error_is_wrapped_without_exposing_original_message(tmp_path) -> None:
    service, _, repository = make_service(
        tmp_path,
        FakeProvider(error=RuntimeError("secret provider detail")),
    )

    with pytest.raises(ReportGenerationError) as caught:
        service.generate("2026-08-05", "记录", None, include_chat=False)

    assert caught.value.code == "report_generation_failed"
    assert "secret provider detail" not in caught.value.safe_message
    with pytest.raises(ReportNotFoundError):
        repository.get("2026-08-05")


def test_regenerate_creates_next_version_with_optimistic_lock(tmp_path) -> None:
    provider = FakeProvider()
    service, _, repository = make_service(tmp_path, provider)
    first = service.generate("2026-08-05", "第一版", None, include_chat=False)
    provider.content = json.dumps(valid_sections(completed=["第二版"]), ensure_ascii=False)

    with pytest.raises(ReportVersionConflictError):
        service.generate("2026-08-05", "冲突", None, include_chat=False)

    second = service.generate(
        "2026-08-05",
        "第二版记录",
        None,
        include_chat=False,
        expected_version=first.current_version,
    )

    assert second.current_version == 2
    assert [item.number for item in second.versions] == [1, 2]
    assert second.current.sections.completed == ("第二版",)
    assert repository.get("2026-08-05").source_notes == "第二版记录"
