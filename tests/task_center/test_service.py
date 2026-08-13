"""Task ledger lifecycle, retention, recovery, and safe persistence tests."""

import json
import multiprocessing
import threading

import pytest

from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_center.repository import TaskLedgerError


def _build_service(tmp_path):
    return TaskCenterService(tmp_path / "tasks")


def _record_tool_in_process(root, task_id, index, start):
    start.wait()
    TaskCenterService(root, recover_unfinished=False).tool_started(task_id, f"process-tool-{index}")


def test_task_lifecycle_records_a_safe_tool_and_approval_timeline(tmp_path):
    service = _build_service(tmp_path)

    task = service.create_task("session-1", "  Read the project status and continue developing.  ")
    service.tool_started(task.id, "mcp__files__read", arguments={"path": "secret.txt"})
    service.approval_requested(task.id, "call-1", "mcp__shell__run", arguments={"command": "secret"})
    service.record_approval(task.id, "call-1", "mcp__shell__run", approved=True)
    service.tool_finished(task.id, "mcp__shell__run", call_id="call-1", duration_ms=31, result={"token": "secret"})
    completed = service.complete(task.id, response_text="The private response text")

    assert task.request_summary == "Read the project status and continue developing."
    assert completed.status == "completed"
    assert completed.finished_at is not None
    assert [event.type for event in completed.events] == [
        "request_submitted",
        "tool_started",
        "approval_requested",
        "approval_approved",
        "tool_succeeded",
        "reply_completed",
    ]
    assert completed.events[1].tool_name == "mcp__files__read"
    assert completed.events[-2].duration_ms == 31

    raw_ledger = (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")
    for secret in ("secret.txt", '"secret"', "private response"):
        assert secret not in raw_ledger.lower()


def test_failure_and_interruption_are_terminal_and_keep_only_safe_labels(tmp_path):
    service = _build_service(tmp_path)

    failed = service.create_task("session-1", "fail me")
    stopped = service.create_task("session-2", "stop me")
    service.fail(failed.id, exception=RuntimeError("database password: secret"))
    service.stop(stopped.id)

    assert service.get_task(failed.id).status == "failed"
    assert service.get_task(failed.id).events[-1].label == "任务执行失败"
    assert service.get_task(stopped.id).status == "stopped"
    assert service.get_task(stopped.id).events[-1].label == "执行已中断"
    raw_ledger = (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")
    assert "database password" not in raw_ledger


def test_retention_limits_events_and_tasks_to_the_most_recent_100(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "many events")
    for index in range(101):
        service.tool_started(task.id, f"tool-{index}")

    assert len(service.get_task(task.id).events) == 100
    assert service.get_task(task.id).events[-1].tool_name == "tool-100"

    for index in range(100):
        service.create_task("session", f"task {index}")

    tasks = service.list_tasks(limit=100)
    assert len(tasks) == 100
    assert tasks[0].request_summary == "task 99"
    assert all(not item.events for item in tasks)


def test_restart_stops_unfinished_tasks_and_persists_a_safe_recovery_event(tmp_path):
    service = _build_service(tmp_path)
    running = service.create_task("session-1", "running")
    waiting = service.create_task("session-2", "waiting")
    service.approval_requested(waiting.id, "call-1", "mcp__tool")

    restarted = _build_service(tmp_path)

    for task_id in (running.id, waiting.id):
        recovered = restarted.get_task(task_id)
        assert recovered.status == "stopped"
        assert recovered.finished_at is not None
        assert recovered.events[-1].type == "execution_interrupted"
        assert recovered.events[-1].label == "服务重启，执行未完成"


def test_list_filter_persistence_and_missing_task(tmp_path):
    service = _build_service(tmp_path)
    first = service.create_task("session-a", "one")
    service.create_task("session-b", "two")

    assert [task.id for task in service.list_tasks(session_id="session-a")] == [first.id]
    assert TaskCenterService(tmp_path / "tasks").get_task(first.id).request_summary == "one"
    assert service.get_task("missing") is None
    assert json.loads((tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8"))["tasks"]


def test_concurrent_event_updates_do_not_lose_ledger_entries(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "concurrent tools")
    barrier = threading.Barrier(11)

    def record(index):
        barrier.wait()
        service.tool_started(task.id, f"tool-{index}")

    workers = [threading.Thread(target=record, args=(index,)) for index in range(10)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    persisted = service.get_task(task.id)
    assert len(persisted.events) == 11
    assert {event.tool_name for event in persisted.events if event.tool_name} == {
        f"tool-{index}" for index in range(10)
    }


def test_awaiting_approval_requires_recorded_decision_before_progressing(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "approval required")
    service.approval_requested(task.id, "call-1", "mcp__shell__run")

    with pytest.raises(ValueError, match="审批"):
        service.tool_finished(task.id, "mcp__shell__run")
    with pytest.raises(ValueError, match="审批"):
        service.complete(task.id)
    with pytest.raises(ValueError, match="审批"):
        service.tool_started(task.id, "mcp__files__read")

    service.record_approval(task.id, "call-1", "mcp__shell__run", approved=True)
    assert service.tool_finished(task.id, "mcp__shell__run", call_id="call-1").status == "running"
    assert service.complete(task.id).status == "completed"


def test_corrupt_ledger_raises_instead_of_overwriting_existing_history(tmp_path):
    service = _build_service(tmp_path)
    service.create_task("session", "preserve me")
    ledger_path = tmp_path / "tasks" / "tasks.json"
    ledger_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(TaskLedgerError, match="账本"):
        _build_service(tmp_path)
    with pytest.raises(TaskLedgerError, match="账本"):
        service.create_task("session", "must not overwrite")
    assert ledger_path.read_text(encoding="utf-8") == "{not valid json"


@pytest.mark.parametrize("payload", ["[]", '{"tasks": {}}', '{"tasks": ["not a task"]}'])
def test_invalid_ledger_shapes_raise_instead_of_becoming_an_empty_ledger(tmp_path, payload):
    ledger_root = tmp_path / "tasks"
    ledger_root.mkdir()
    ledger_path = ledger_root / "tasks.json"
    ledger_path.write_text(payload, encoding="utf-8")

    with pytest.raises(TaskLedgerError, match="账本"):
        _build_service(tmp_path)
    assert ledger_path.read_text(encoding="utf-8") == payload


def test_rejected_approval_call_cannot_finish_a_tool_and_approved_call_must_match(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "two approvals")
    service.approval_requested(task.id, "call-rejected", "mcp__shell__run")
    service.record_approval(task.id, "call-rejected", "mcp__shell__run", approved=False)

    with pytest.raises(ValueError, match="拒绝"):
        service.tool_finished(task.id, "mcp__shell__run", call_id="call-rejected")

    service.approval_requested(task.id, "call-approved", "mcp__shell__run")
    service.record_approval(task.id, "call-approved", "mcp__shell__run", approved=True)
    with pytest.raises(ValueError, match="调用 ID"):
        service.tool_finished(task.id, "mcp__shell__run", call_id="call-other")
    assert service.tool_finished(task.id, "mcp__shell__run", call_id="call-approved").events[-1].type == "tool_succeeded"
    with pytest.raises(ValueError, match="已完成"):
        service.tool_finished(task.id, "mcp__shell__run", call_id="call-approved")


def test_concurrent_tool_finish_consumes_an_approved_call_once(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "one approved call")
    service.approval_requested(task.id, "call-1", "mcp__shell__run")
    service.record_approval(task.id, "call-1", "mcp__shell__run", approved=True)
    barrier = threading.Barrier(3)
    results = []

    def finish():
        barrier.wait()
        try:
            service.tool_finished(task.id, "mcp__shell__run", call_id="call-1")
            results.append("success")
        except ValueError:
            results.append("rejected")

    workers = [threading.Thread(target=finish) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    assert sorted(results) == ["rejected", "success"]
    assert [event.type for event in service.get_task(task.id).events].count("tool_succeeded") == 1


def test_cross_process_event_updates_do_not_lose_ledger_entries(tmp_path):
    service = _build_service(tmp_path)
    task = service.create_task("session", "cross process")
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    workers = [
        context.Process(target=_record_tool_in_process, args=(tmp_path / "tasks", task.id, index, start))
        for index in range(3)
    ]
    for worker in workers:
        worker.start()
    start.set()
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0

    assert {event.tool_name for event in service.get_task(task.id).events if event.tool_name} == {
        "process-tool-0", "process-tool-1", "process-tool-2"
    }


@pytest.mark.parametrize(
    "events",
    [
        {"not": "a list"},
        ["not an event"],
        [{"id": "event-1", "type": "tool_started", "label": "x", "created_at": 123}],
        [{"id": "event-1", "type": "tool_started", "label": "x"}],
    ],
)
def test_invalid_event_shapes_raise_instead_of_silently_dropping_history(tmp_path, events):
    ledger_root = tmp_path / "tasks"
    ledger_root.mkdir()
    payload = {
        "tasks": [{
            "id": "task-1",
            "session_id": "session",
            "request_summary": "request",
            "status": "running",
            "created_at": "2026-08-13T00:00:00+00:00",
            "updated_at": "2026-08-13T00:00:00+00:00",
            "events": events,
        }]
    }
    ledger_path = ledger_root / "tasks.json"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TaskLedgerError, match="账本"):
        _build_service(tmp_path)
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["tasks"][0]["events"] == events
