from __future__ import annotations

import pytest

from iris_agent.reports.errors import ReportValidationError
from iris_agent.reports.models import (
    DailyReport,
    ReportSections,
    ReportSourceMessage,
    ReportVersion,
)


def make_version(number: int = 1) -> ReportVersion:
    return ReportVersion(
        number=number,
        sections=ReportSections(completed=("完成日报设计",)),
        kind="generated",
        instruction=None,
        created_at=float(number),
    )


def test_report_sections_copy_and_normalize_input() -> None:
    source = ["  完成日报设计  ", "", "   "]
    sections = ReportSections.from_mapping(
        {
            "completed": source,
            "in_progress": [],
            "problems": [],
            "next_day": [],
            "assistance": [],
        }
    )

    source.append("外部修改")

    assert sections.completed == ("完成日报设计",)


def test_report_sections_require_exact_string_array_fields() -> None:
    with pytest.raises(ReportValidationError, match="章节字段"):
        ReportSections.from_mapping({"completed": []})

    with pytest.raises(ReportValidationError, match="字符串数组"):
        ReportSections.from_mapping(
            {
                "completed": [1],
                "in_progress": [],
                "problems": [],
                "next_day": [],
                "assistance": [],
            }
        )


def test_report_source_message_rejects_non_chat_roles() -> None:
    with pytest.raises(ReportValidationError, match="来源消息角色"):
        ReportSourceMessage(role="tool", content="secret")  # type: ignore[arg-type]


def test_daily_report_validates_date_and_current_version() -> None:
    with pytest.raises(ReportValidationError, match="日期"):
        DailyReport.create("2026-13-40", "记录", None, (), (make_version(),), 1)

    with pytest.raises(ReportValidationError, match="当前日报版本"):
        DailyReport.create("2026-08-05", "记录", None, (), (), 1)


def test_daily_report_rejects_duplicate_version_numbers() -> None:
    with pytest.raises(ReportValidationError, match="版本号不能重复"):
        DailyReport.create(
            "2026-08-05",
            "记录",
            None,
            (),
            (make_version(1), make_version(1)),
            1,
        )


def test_daily_report_copies_sources_and_versions() -> None:
    sources = [ReportSourceMessage("user", "完成接口")]
    versions = [make_version()]

    report = DailyReport.create(
        "2026-08-05",
        "记录",
        "session_1",
        sources,
        versions,
        1,
        created_at=10.0,
        updated_at=11.0,
    )
    sources.append(ReportSourceMessage("assistant", "新增内容"))
    versions.append(make_version(2))

    assert report.source_chat_snapshot == (ReportSourceMessage("user", "完成接口"),)
    assert [item.number for item in report.versions] == [1]
    assert report.current.number == 1
    assert report.created_at == 10.0
    assert report.updated_at == 11.0


def test_report_version_validates_kind_and_positive_number() -> None:
    with pytest.raises(ReportValidationError, match="版本号"):
        make_version(0)

    with pytest.raises(ReportValidationError, match="版本类型"):
        ReportVersion(1, ReportSections(), "unknown", None, 1.0)  # type: ignore[arg-type]
