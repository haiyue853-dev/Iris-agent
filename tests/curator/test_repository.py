"""Curator 仓储测试：每条报告一文件 + 裁剪 + 容错。"""

from __future__ import annotations

import pytest

from iris_agent.curator.models import CuratorReport
from iris_agent.curator.repository import CuratorRepository, CuratorRepositoryError


def _report(report_id: str = "cur-0123456789ab", created_at: str = "2026-08-16T00:00:00+00:00") -> CuratorReport:
    return CuratorReport(id=report_id, status="open", created_at=created_at, summary="x", suggestions=[])


def test_save_and_get_roundtrip(tmp_path):
    repo = CuratorRepository(tmp_path)
    report = _report()
    repo.save(report)
    assert repo.get(report.id) == report


def test_get_missing_returns_none(tmp_path):
    repo = CuratorRepository(tmp_path)
    assert repo.get("cur-ffffffffffff") is None


def test_list_sorted_by_created_at_desc(tmp_path):
    repo = CuratorRepository(tmp_path)
    repo.save(_report("cur-000000000001", "2026-08-15T00:00:00+00:00"))
    repo.save(_report("cur-000000000002", "2026-08-17T00:00:00+00:00"))
    repo.save(_report("cur-000000000003", "2026-08-16T00:00:00+00:00"))
    ids = [r.id for r in repo.list()]
    assert ids == ["cur-000000000002", "cur-000000000003", "cur-000000000001"]


def test_trim_enforces_max_reports(tmp_path):
    repo = CuratorRepository(tmp_path, max_reports=2)
    for i in range(4):
        repo.save(_report(f"cur-{i:012d}", f"2026-08-1{i}T00:00:00+00:00"))
    remaining = repo.list()
    assert len(remaining) == 2
    # 保留最新的两份
    assert {r.id for r in remaining} == {f"cur-{i:012d}" for i in (2, 3)}


def test_list_ignores_corrupt_files(tmp_path):
    repo = CuratorRepository(tmp_path)
    (tmp_path / "bad.json").write_text("{invalid", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not json", encoding="utf-8")
    repo.save(_report())
    assert {r.id for r in repo.list()} == {"cur-0123456789ab"}


def test_rejects_path_traversal(tmp_path):
    repo = CuratorRepository(tmp_path)
    with pytest.raises(CuratorRepositoryError):
        repo.get("../etc/passwd")
