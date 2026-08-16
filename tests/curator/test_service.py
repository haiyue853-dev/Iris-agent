"""Curator 服务测试：run 只读、apply/dismiss 与降级。"""

from __future__ import annotations

import pytest

from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.service import CuratorReportNotFoundError, CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService


class FakeExtractor:
    def extract(self, dialogue):
        return None


class FakeEmbedder:
    def __init__(self, vectors=None, error=False):
        self._vectors = vectors or {}
        self.error = error

    def embed(self, texts):
        if self.error:
            raise RuntimeError("embed failed")
        return [self._vectors.get(t, [1.0, 0.0]) for t in texts]


class FakeReferee:
    def __init__(self, label="conflict"):
        self.label = label

    def judge(self, a, b):
        return self.label


def _memory(tmp_path) -> MemoryService:
    return MemoryService(MemoryRepository(tmp_path / "memory"))


def _profile(tmp_path) -> ProfileService:
    return ProfileService(ProfileRepository(tmp_path / "profile"), FakeExtractor(), enabled=False)


def _service(tmp_path, embedder, referee=None, enable_llm=False, max_pairs_per_run=200) -> CuratorService:
    engine = SimilarityEngine(embedder=embedder, merge_threshold=0.85, conflict_threshold=0.45)
    return CuratorService(
        CuratorRepository(tmp_path / "curator"),
        _memory(tmp_path),
        _profile(tmp_path),
        engine,
        referee=referee,
        enable_llm=enable_llm,
        max_pairs_per_run=max_pairs_per_run,
    )


def test_run_finds_duplicate_memories(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)

    report = service.run()

    assert len(report.suggestions) == 1
    suggestion = report.suggestions[0]
    assert suggestion.kind == "merge"
    assert suggestion.scope == "memory"
    assert suggestion.reason == "embedding"


def test_run_is_read_only(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)

    before = [entry.id for entry in memory.list()]
    service.run()
    after = [entry.id for entry in memory.list()]

    assert before == after  # 审查不删改任何数据


def test_apply_deletes_drop_memory(tmp_path):
    memory = _memory(tmp_path)
    older = memory.add("用户偏好 React", "preference")
    newer = memory.add("用户偏好 React 框架", "preference")
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)
    report = service.run()

    applied = service.apply(report.id)

    assert applied == 1
    remaining = [entry.id for entry in memory.list()]
    assert remaining == [newer.id]
    assert older.id not in remaining


def test_run_finds_duplicate_profile_items(tmp_path):
    profile = _profile(tmp_path)
    profile.replace("", ["喜欢 React", "偏好 React 框架"], [], "", [])
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)

    report = service.run()

    assert len(report.suggestions) == 1
    suggestion = report.suggestions[0]
    assert suggestion.kind == "dedupe"
    assert suggestion.scope == "profile"
    assert suggestion.field == "preferences"


def test_apply_removes_profile_item(tmp_path):
    profile = _profile(tmp_path)
    profile.replace("", ["喜欢 React", "偏好 React 框架"], [], "", [])
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)
    report = service.run()

    applied = service.apply(report.id)

    assert applied == 1
    assert profile.get().preferences == ["喜欢 React"]


def test_run_conflict_via_referee(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 Vue", "preference")
    embedder = FakeEmbedder(vectors={"用户偏好 React": [1.0, 0.0], "用户偏好 Vue": [0.5, 0.8660254]})
    service = _service(tmp_path, embedder, referee=FakeReferee("conflict"), enable_llm=True)

    report = service.run()

    assert len(report.suggestions) == 1
    assert report.suggestions[0].kind == "conflict"
    assert report.suggestions[0].reason == "llm"


def test_llm_disabled_skips_review_pairs(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 Vue", "preference")
    embedder = FakeEmbedder(vectors={"用户偏好 React": [1.0, 0.0], "用户偏好 Vue": [0.5, 0.8660254]})
    service = _service(tmp_path, embedder, referee=FakeReferee("conflict"), enable_llm=False)

    report = service.run()

    assert report.suggestions == []


def test_dismiss_marks_suggestions(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)
    report = service.run()

    dismissed = service.dismiss(report.id)

    assert dismissed == 1
    updated = service.get_report(report.id)
    assert updated.suggestions[0].dismissed is True
    assert updated.status == "dismissed"


def test_apply_missing_target_skips(tmp_path):
    memory = _memory(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)
    report = service.run()

    # 目标记忆已在外界被删除，apply 应跳过而不抛错
    for entry in memory.list():
        memory.delete(entry.id)
    applied = service.apply(report.id)

    assert applied == 0


def test_empty_data_returns_empty_report(tmp_path):
    service = _service(tmp_path, FakeEmbedder(), enable_llm=False)
    report = service.run()
    assert report.suggestions == []
    assert "未发现" in report.summary


def test_get_report_missing_raises(tmp_path):
    service = _service(tmp_path, FakeEmbedder())
    with pytest.raises(CuratorReportNotFoundError):
        service.get_report("cur-ffffffffffff")
