from __future__ import annotations

import json

import pytest

from iris_agent.core.models import ProviderResponse
from iris_agent.reports.errors import ReportVersionConflictError
from iris_agent.reports.attachments import ReportAttachment
from iris_agent.reports.models import ReportSections
from iris_agent.reports.repository import JsonDailyReportRepository
from iris_agent.reports.service import DailyReportService
from iris_agent.sessions.json_store import JsonSessionRepository


class _Provider:
    def complete(self, _messages, _tools):
        return ProviderResponse(content=json.dumps({
            "completed": ["初始版本"],
            "in_progress": [],
            "problems": [],
            "next_day": [],
            "assistance": [],
        }, ensure_ascii=False))


def _service(tmp_path) -> DailyReportService:
    return DailyReportService(
        _Provider(),
        JsonSessionRepository(tmp_path / "sessions"),
        JsonDailyReportRepository(tmp_path / "reports"),
        clock=lambda: 100.0,
    )


def test_restore_invalidates_a_stale_write_token_even_when_it_returns_to_v1(tmp_path) -> None:
    service = _service(tmp_path)
    first = service.generate("2026-08-05", "记录", None, include_chat=False)
    second = service.save_manual(
        "2026-08-05",
        ReportSections(completed=("第二版",)),
        expected_version=first.current_version,
    )

    restored = service.restore("2026-08-05", 1, expected_version=second.current_version)

    assert restored.current_version == 1
    with pytest.raises(ReportVersionConflictError):
        service.save_manual(
            "2026-08-05",
            ReportSections(completed=("来自旧页面的修改",)),
            expected_version=first.current_version,
        )


def test_edit_after_restore_keeps_existing_attachment_metadata(tmp_path) -> None:
    service = _service(tmp_path)
    repository = service.repository
    first = service.generate("2026-08-05", "记录", None, include_chat=False)
    attachment = ReportAttachment(
        id="a7db5fa3-b126-4ffc-a7b6-2d73d07dd2e1",
        original_name="work-notes.txt",
        media_type="text/plain",
        size_bytes=5,
        preserve=False,
        status="temporary",
        extracted_text="要保留的附件元数据",
        created_at=101.0,
    )
    with_attachment = repository.get("2026-08-05")
    with_attachment.attachments.append(attachment)
    with_attachment.revision += 1
    repository.save(with_attachment, expected_revision=first.revision)
    second = service.save_manual(
        "2026-08-05",
        ReportSections(completed=("第二版",)),
        expected_version=with_attachment.revision,
    )
    restored = service.restore("2026-08-05", 1, expected_version=second.revision)

    edited = service.save_manual(
        "2026-08-05",
        ReportSections(completed=("恢复后编辑",)),
        expected_version=restored.revision,
    )

    assert edited.attachments == [attachment]


def test_regenerating_an_existing_report_keeps_attachment_metadata(tmp_path) -> None:
    service = _service(tmp_path)
    repository = service.repository
    first = service.generate("2026-08-05", "记录", None, include_chat=False)
    attachment = ReportAttachment(
        id="e8f4e291-0e71-4d6a-b9f5-3310f3700d3e",
        original_name="work-notes.txt",
        media_type="text/plain",
        size_bytes=5,
        preserve=False,
        status="temporary",
        extracted_text="附件内容",
        created_at=101.0,
    )
    with_attachment = repository.get("2026-08-05")
    with_attachment.attachments.append(attachment)
    with_attachment.revision += 1
    repository.save(with_attachment, expected_revision=first.revision)

    regenerated = service.generate(
        "2026-08-05",
        "重新生成",
        None,
        include_chat=False,
        expected_version=with_attachment.revision,
    )

    assert regenerated.attachments == [attachment]
