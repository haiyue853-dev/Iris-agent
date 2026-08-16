"""Curator 定时调度测试：到点运行 + 有建议时发通知。"""

from __future__ import annotations

from datetime import datetime

from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.scheduler import CuratorScheduler
from iris_agent.curator.service import CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.notifications.service import NotificationService
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService


class FakeExtractor:
    def extract(self, dialogue):
        return None


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _curator(tmp_path) -> CuratorService:
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    profile = ProfileService(ProfileRepository(tmp_path / "profile"), FakeExtractor(), enabled=False)
    engine = SimilarityEngine(embedder=FakeEmbedder())
    return CuratorService(CuratorRepository(tmp_path / "curator"), memory, profile, engine, enable_llm=False)


def test_scheduler_runs_and_notifies_when_suggestions(tmp_path):
    curator = _curator(tmp_path)
    curator.memory.add("用户偏好 React", "preference")
    curator.memory.add("用户偏好 React 框架", "preference")
    notifications = NotificationService(tmp_path / "notifications")
    scheduler = CuratorScheduler(curator, notifications, schedule="* * * * *")

    ran = scheduler.run_pending(datetime(2026, 8, 16, 10, 30))

    assert ran == 1
    assert len(notifications.list_notifications()) == 1
    notification = notifications.list_notifications()[0]
    assert notification.title == "数据审查提醒"


def test_scheduler_does_not_notify_without_suggestions(tmp_path):
    curator = _curator(tmp_path)
    notifications = NotificationService(tmp_path / "notifications")
    scheduler = CuratorScheduler(curator, notifications, schedule="* * * * *")

    ran = scheduler.run_pending(datetime(2026, 8, 16, 10, 30))

    assert ran == 0
    assert notifications.list_notifications() == []


def test_scheduler_skips_when_schedule_does_not_match(tmp_path):
    curator = _curator(tmp_path)
    curator.memory.add("用户偏好 React", "preference")
    curator.memory.add("用户偏好 React 框架", "preference")
    notifications = NotificationService(tmp_path / "notifications")
    scheduler = CuratorScheduler(curator, notifications, schedule="0 3 * * *")

    ran = scheduler.run_pending(datetime(2026, 8, 16, 10, 30))

    assert ran == 0
    assert notifications.list_notifications() == []


def test_scheduler_deduplicates_same_window(tmp_path):
    curator = _curator(tmp_path)
    curator.memory.add("用户偏好 React", "preference")
    curator.memory.add("用户偏好 React 框架", "preference")
    notifications = NotificationService(tmp_path / "notifications")
    scheduler = CuratorScheduler(curator, notifications, schedule="* * * * *")

    first = scheduler.run_pending(datetime(2026, 8, 16, 10, 30))
    second = scheduler.run_pending(datetime(2026, 8, 16, 10, 30))

    assert first == 1
    assert second == 0  # 同一分钟窗口不重复跑
    assert len(notifications.list_notifications()) == 1
