from datetime import datetime

import pytest

from iris_agent.automation.service import AutomationScheduler, AutomationService
from iris_agent.hot_radar.service import HotRadarService


def test_task_and_execution_ledger_survive_restart(tmp_path):
    radar = HotRadarService(tmp_path / "radar", sources={"tech": lambda: [{"title": "AI 更新", "url": "https://example.test/ai", "source": "Tech", "summary": "摘要"}]})
    radar.create_subscription("AI")
    service = AutomationService(tmp_path / "automation", radar)

    task = service.create_task("每小时扫描", "0 * * * *")
    execution = service.run_now(task.id)

    assert execution.status == "succeeded"
    restarted = AutomationService(tmp_path / "automation", radar)
    assert restarted.list_tasks()[0].enabled is True
    assert restarted.list_executions(task.id)[0].summary == "新增 1 条热点"


def test_running_execution_is_marked_unknown_on_restart_and_terminal_status_is_immutable(tmp_path):
    radar = HotRadarService(tmp_path / "radar", sources={})
    service = AutomationService(tmp_path / "automation", radar)
    task = service.create_task("扫描", "*/30 * * * *")
    execution = service.claim(task.id, "manual")

    restarted = AutomationService(tmp_path / "automation", radar)
    recovered = restarted.list_executions(task.id)[0]

    assert execution.status == "running"
    assert recovered.status == "unknown"


def test_scheduler_runs_matching_task_once_per_minute(tmp_path):
    radar = HotRadarService(tmp_path / "radar", sources={})
    service = AutomationService(tmp_path / "automation", radar)
    task = service.create_task("hourly scan", "5 * * * *")
    scheduler = AutomationScheduler(service)

    assert scheduler.run_pending(datetime(2026, 8, 13, 9, 5)) == 1
    assert scheduler.run_pending(datetime(2026, 8, 13, 9, 5)) == 0
    assert scheduler.run_pending(datetime(2026, 8, 13, 9, 6)) == 0
    assert service.list_executions(task.id)[0].status == "succeeded"


def test_scheduler_supports_step_from_a_specific_start(tmp_path):
    service = AutomationService(tmp_path / "automation", HotRadarService(tmp_path / "radar", sources={}))
    task = service.create_task("stepped", "5/10 * * * *")
    scheduler = AutomationScheduler(service)

    assert scheduler.run_pending(datetime(2026, 8, 13, 9, 15)) == 1
    assert service.list_executions(task.id)[0].task_id == task.id


def test_scheduler_does_not_repeat_a_window_after_restart(tmp_path):
    service = AutomationService(tmp_path / "automation", HotRadarService(tmp_path / "radar", sources={}))
    service.create_task("hourly", "5 * * * *")
    moment = datetime(2026, 8, 13, 9, 5)

    assert AutomationScheduler(service).run_pending(moment) == 1
    assert AutomationScheduler(AutomationService(tmp_path / "automation", service.radar)).run_pending(moment) == 0


def test_task_rejects_cron_fields_the_scheduler_cannot_run(tmp_path):
    service = AutomationService(tmp_path / "automation", HotRadarService(tmp_path / "radar", sources={}))

    with pytest.raises(ValueError):
        service.create_task("invalid", "today at nine every day")
