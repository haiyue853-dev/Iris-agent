"""Curator 服务测试：run 只读、apply/dismiss 与降级。"""

from __future__ import annotations

import pytest

from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.service import CuratorReportNotFoundError, CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.knowledge.repository import KnowledgeRepository
from iris_agent.knowledge.retriever import KeywordRetriever
from iris_agent.knowledge.service import KnowledgeService
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService
from iris_agent.skill_center.service import SkillCenterService


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


def _skills(tmp_path) -> SkillCenterService:
    return SkillCenterService(
        catalog_root=tmp_path / "bundled",
        settings_file=tmp_path / "skills_state.json",
        user_directory=tmp_path / "user_skills",
        max_body_chars=4000,
    )


def _knowledge(tmp_path) -> KnowledgeService:
    repository = KnowledgeRepository(tmp_path / "knowledge")
    retriever = KeywordRetriever(repository.list, max_hit_chars=500)
    return KnowledgeService(repository, retriever)


def _service(tmp_path, embedder, referee=None, enable_llm=False, max_pairs_per_run=200, skills=None, knowledge=None, expire_days=90) -> CuratorService:
    engine = SimilarityEngine(embedder=embedder, merge_threshold=0.85, conflict_threshold=0.45)
    return CuratorService(
        CuratorRepository(tmp_path / "curator"),
        _memory(tmp_path),
        _profile(tmp_path),
        engine,
        skills=skills,
        knowledge=knowledge,
        referee=referee,
        enable_llm=enable_llm,
        max_pairs_per_run=max_pairs_per_run,
        expire_days=expire_days,
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


def test_run_finds_duplicate_skills(tmp_path):
    skills = _skills(tmp_path)
    skills.save_user_skill("React 技巧", "前端", "如何使用 React hooks 组织组件状态")
    skills.save_user_skill("React 技能", "前端", "如何使用 React hooks 管理组件状态")
    service = _service(tmp_path, FakeEmbedder(), skills=skills, enable_llm=False)

    report = service.run()

    skill_suggestions = [s for s in report.suggestions if s.scope == "skill"]
    assert len(skill_suggestions) == 1
    assert skill_suggestions[0].kind == "dedupe"


def test_apply_deletes_drop_skill(tmp_path):
    skills = _skills(tmp_path)
    first = skills.save_user_skill("React 技巧", "前端", "如何使用 React hooks 组织组件状态")
    skills.save_user_skill("React 技能", "前端", "如何使用 React hooks 管理组件状态")
    service = _service(tmp_path, FakeEmbedder(), skills=skills, enable_llm=False)
    report = service.run()

    applied = service.apply(report.id)

    assert applied == 1
    remaining = {s.id for s in skills.list_user_definitions()}
    assert first.id not in remaining


def test_run_finds_duplicate_knowledge(tmp_path):
    knowledge = _knowledge(tmp_path)
    knowledge.add("多模态存储", "多模态大模型的图文信息组织方式")
    knowledge.add("多模态存储2", "多模态大模型的图文信息组织方式")
    service = _service(tmp_path, FakeEmbedder(), knowledge=knowledge, enable_llm=False)

    report = service.run()

    knowledge_suggestions = [s for s in report.suggestions if s.scope == "knowledge" and s.kind != "expire"]
    assert len(knowledge_suggestions) == 1
    assert knowledge_suggestions[0].kind == "dedupe"


def test_apply_deletes_drop_knowledge(tmp_path):
    knowledge = _knowledge(tmp_path)
    knowledge.add("多模态存储", "多模态大模型的图文信息组织方式")
    knowledge.add("多模态存储2", "多模态大模型的图文信息组织方式")
    service = _service(tmp_path, FakeEmbedder(), knowledge=knowledge, enable_llm=False)
    report = service.run()

    applied = service.apply(report.id)

    assert applied == 1
    assert len(knowledge.list()) == 1


def test_run_suggests_expired_knowledge(tmp_path):
    import time
    from dataclasses import replace

    knowledge = _knowledge(tmp_path)
    entry = knowledge.add("旧面经", "某公司 2024 年面试题")
    knowledge.repository.save(replace(entry, created_at=time.time() - 2 * 86400))
    service = _service(tmp_path, FakeEmbedder(), knowledge=knowledge, enable_llm=False, expire_days=1)

    report = service.run()

    expire_suggestions = [s for s in report.suggestions if s.kind == "expire"]
    assert len(expire_suggestions) == 1
    assert expire_suggestions[0].scope == "knowledge"
    assert expire_suggestions[0].reason == "age"


def test_apply_deletes_expired_knowledge(tmp_path):
    import time
    from dataclasses import replace

    knowledge = _knowledge(tmp_path)
    entry = knowledge.add("旧面经", "某公司 2024 年面试题")
    knowledge.repository.save(replace(entry, created_at=time.time() - 2 * 86400))
    service = _service(tmp_path, FakeEmbedder(), knowledge=knowledge, enable_llm=False, expire_days=1)
    report = service.run()

    applied = service.apply(report.id)

    assert applied == 1
    assert knowledge.list() == []


def test_expire_disabled_when_days_non_positive(tmp_path):
    import time
    from dataclasses import replace

    knowledge = _knowledge(tmp_path)
    entry = knowledge.add("旧面经", "某公司 2024 年面试题")
    knowledge.repository.save(replace(entry, created_at=time.time() - 2 * 86400))
    service = _service(tmp_path, FakeEmbedder(), knowledge=knowledge, enable_llm=False, expire_days=0)

    report = service.run()

    assert [s for s in report.suggestions if s.kind == "expire"] == []
