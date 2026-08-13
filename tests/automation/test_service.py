from iris_agent.automation.service import AutomationService
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
