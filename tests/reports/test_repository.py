from __future__ import annotations

import os
from pathlib import Path
import threading

import pytest

from iris_agent.reports.errors import (
    ReportNotFoundError,
    ReportStorageError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.attachments import ReportAttachment
from iris_agent.reports.models import DailyReport, ReportSections, ReportVersion
from iris_agent.reports.repository import JsonDailyReportRepository


def version(number: int, text: str | None = None) -> ReportVersion:
    return ReportVersion(
        number=number,
        sections=ReportSections(completed=(text or f"版本 {number}",)),
        kind="generated" if number == 1 else "manual",
        instruction=None,
        created_at=float(number),
    )


def report_with_versions(
    report_date: str = "2026-08-05",
    numbers: tuple[int, ...] = (1,),
    revision: int | None = None,
) -> DailyReport:
    versions = tuple(version(number) for number in numbers)
    return DailyReport.create(
        report_date,
        "工作记录",
        None,
        (),
        versions,
        numbers[-1],
        created_at=1.0,
        updated_at=float(numbers[-1]),
        revision=revision,
    )


def test_repository_round_trip_uses_atomic_replace_and_fsync(tmp_path, monkeypatch) -> None:
    real_replace = os.replace
    real_fsync = os.fsync
    replace_calls: list[tuple[Path, Path]] = []
    fsync_calls: list[int] = []

    def replace_spy(source, target):
        replace_calls.append((Path(source), Path(target)))
        real_replace(source, target)

    def fsync_spy(fd: int):
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "replace", replace_spy)
    monkeypatch.setattr(os, "fsync", fsync_spy)
    repository = JsonDailyReportRepository(tmp_path)

    repository.save(report_with_versions())
    restored = repository.get("2026-08-05")

    assert restored.current.sections.completed == ("版本 1",)
    assert replace_calls[0][0].parent == tmp_path
    assert replace_calls[0][1] == tmp_path / "2026-08-05.json"
    assert fsync_calls


def test_repository_persists_report_attachment_metadata_without_a_file_path(tmp_path) -> None:
    attachment = ReportAttachment(
        id="a7db5fa3-b126-4ffc-a7b6-2d73d07dd2e1", original_name="notes.txt", media_type="text/plain",
        size_bytes=5, preserve=True, status="preserved", extracted_text="done", created_at=2.0,
    )
    report = report_with_versions()
    report.attachments.append(attachment)
    repository = JsonDailyReportRepository(tmp_path)

    repository.save(report)

    payload = (tmp_path / "2026-08-05.json").read_text(encoding="utf-8")
    assert "attachments" in payload
    assert "file_name" not in payload
    assert repository.get("2026-08-05").attachments == [attachment]


def test_repository_reads_legacy_report_without_attachments(tmp_path) -> None:
    import json
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions())
    path = tmp_path / "2026-08-05.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["attachments"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert repository.get("2026-08-05").attachments == []


def test_legacy_report_without_revision_uses_its_highest_history_version(tmp_path) -> None:
    import json

    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions(numbers=(1, 2), revision=2))
    path = tmp_path / "2026-08-05.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["revision"]
    payload["current_version"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = repository.get("2026-08-05")

    assert legacy.current_version == 1
    assert legacy.revision == 2
    legacy.revision += 1
    repository.save(legacy, expected_revision=2)
    assert json.loads(path.read_text(encoding="utf-8"))["revision"] == 3


def test_repository_lists_reports_by_updated_time(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions("2026-08-04", (1,)))
    repository.save(report_with_versions("2026-08-05", (1, 2)))

    assert [item.date for item in repository.list()] == ["2026-08-05", "2026-08-04"]


def test_repository_rejects_invalid_and_unknown_dates(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path)

    with pytest.raises(ReportValidationError) as invalid:
        repository.get("../../secret")
    assert invalid.value.code == "report_invalid_date"

    with pytest.raises(ReportNotFoundError):
        repository.get("2026-08-05")


def test_corrupt_report_is_not_overwritten(tmp_path) -> None:
    path = tmp_path / "2026-08-05.json"
    path.write_text("{broken", encoding="utf-8")
    repository = JsonDailyReportRepository(tmp_path)

    with pytest.raises(ReportStorageError):
        repository.get("2026-08-05")

    assert path.read_text(encoding="utf-8") == "{broken"


def test_existing_report_requires_matching_expected_version(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions(numbers=(1,)))

    with pytest.raises(ReportVersionConflictError):
        repository.save(report_with_versions(numbers=(1, 2)), expected_version=None)
    with pytest.raises(ReportVersionConflictError):
        repository.save(report_with_versions(numbers=(1, 2)), expected_version=9)

    repository.save(report_with_versions(numbers=(1, 2)), expected_version=1)
    assert repository.get("2026-08-05").current_version == 2


def test_failed_replace_keeps_previous_report(tmp_path, monkeypatch) -> None:
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions(numbers=(1,)))

    def fail_replace(_source, _target):
        raise OSError("disk unavailable")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ReportStorageError):
        repository.save(report_with_versions(numbers=(1, 2)), expected_version=1)

    assert repository.get("2026-08-05").current_version == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_repository_trims_old_versions_but_keeps_current(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path, max_versions=2)
    repository.save(report_with_versions(numbers=(1, 2, 3)))

    restored = repository.get("2026-08-05")

    assert [item.number for item in restored.versions] == [2, 3]
    assert restored.current_version == 3


def test_concurrent_writers_cannot_both_commit_same_expected_version(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions(numbers=(1,)))
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def save_candidate(candidate: DailyReport) -> None:
        barrier.wait()
        try:
            repository.save(candidate, expected_version=1)
            outcomes.append("saved")
        except ReportVersionConflictError:
            outcomes.append("conflict")

    first = threading.Thread(target=save_candidate, args=(report_with_versions(numbers=(1, 2), revision=2),))
    second = threading.Thread(target=save_candidate, args=(report_with_versions(numbers=(1, 3), revision=2),))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(outcomes) == ["conflict", "saved"]


def test_repository_requires_the_next_monotonic_write_revision(tmp_path) -> None:
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(report_with_versions(numbers=(1,), revision=1))

    with pytest.raises(ReportVersionConflictError):
        repository.save(report_with_versions(numbers=(1, 2), revision=1), expected_revision=1)
    with pytest.raises(ReportVersionConflictError):
        repository.save(report_with_versions(numbers=(1, 2), revision=3), expected_revision=1)

    repository.save(report_with_versions(numbers=(1, 2), revision=2), expected_revision=1)
    assert repository.get("2026-08-05").revision == 2
