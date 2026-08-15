from __future__ import annotations

import threading
import time

import pytest

from iris_agent.core.models import AgentEvent
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.models import QueueJob
from iris_agent.task_queue.repository import QueueLedgerError, QueueRepository
from iris_agent.task_queue.service import TaskQueueService


def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


class ControlledAgentService:
    """A deterministic AgentService substitute that exposes worker ordering."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled: list[tuple[str, str]] = []
        self.resolved: list[tuple[str, str, bool]] = []

    def run(self, session_id: str, message: str):
        self.calls.append(message)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if message == "provider-error":
                raise RuntimeError("simulated provider failure")
            if message == "block":
                self.started.set()
                self.release.wait(2)
            if message == "approval":
                yield AgentEvent("tool_started", {"call_id": "call-1", "name": "mcp__shell__run"})
                yield AgentEvent("tool_approval_requested", {"call_id": "call-1", "name": "mcp__shell__run"})
                return
            yield AgentEvent("text_delta", {"content": "private model text"})
            yield AgentEvent("message_completed", {"message_id": f"message-{message}"})
        finally:
            self.active -= 1

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool):
        self.resolved.append((session_id, call_id, approved))
        yield AgentEvent(
            "tool_finished",
            {"call_id": call_id, "name": "mcp__shell__run", "ok": approved},
        )
        yield AgentEvent("message_completed", {"message_id": "after-approval"})

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool:
        self.cancelled.append((session_id, call_id))
        return True


class BlockingRemovalTaskQueueService(TaskQueueService):
    """Expose the old cancel/check-to-remove gap deterministically."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.removal_entered = threading.Event()
        self.release_removal = threading.Event()
        self._block_next_removal = True

    def _remove_job(self, task_id: str) -> None:
        if self._block_next_removal:
            self._block_next_removal = False
            self.removal_entered.set()
            assert self.release_removal.wait(2)
        super()._remove_job(task_id)


class FailingSaveQueueRepository(QueueRepository):
    def save(self, jobs) -> None:
        raise QueueLedgerError("simulated queue ledger failure")


class FailFirstRemovalQueueRepository(QueueRepository):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.save_calls = 0

    def save(self, jobs) -> None:
        self.save_calls += 1
        # submit ×2, first claim, then the first completed-job cleanup.
        if self.save_calls == 4:
            raise QueueLedgerError("simulated cleanup failure")
        super().save(jobs)


class FailFirstClaimQueueRepository(QueueRepository):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.save_calls = 0

    def save(self, jobs) -> None:
        self.save_calls += 1
        # First submit succeeds; first worker claim fails before changing the
        # queued ledger record, then the retry must claim it successfully.
        if self.save_calls == 2:
            raise QueueLedgerError("simulated claim failure")
        super().save(jobs)


class BlockingCreateTaskCenterService(TaskCenterService):
    """Pause a submit after its task exists but before its queue record exists."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.created = threading.Event()
        self.release = threading.Event()
        self.last_task_id: str | None = None

    def create_queued_task(self, session_id: str, user_message: str):
        task = super().create_queued_task(session_id, user_message)
        self.last_task_id = task.id
        self.created.set()
        assert self.release.wait(2)
        return task


class FailFirstTaskCenterFailureService(TaskCenterService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail_calls = 0

    def fail(self, task_id: str, **_ignored):
        self.fail_calls += 1
        if self.fail_calls == 1:
            raise OSError("simulated task ledger failure")
        return super().fail(task_id)


@pytest.fixture
def queue_service(tmp_path):
    tasks = TaskCenterService(tmp_path / "tasks")
    queue = QueueRepository(tmp_path / "queue")
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    yield service, agent, tasks, queue
    service.stop()


def test_worker_executes_jobs_fifo_without_overlapping_agent_runs(queue_service) -> None:
    service, agent, tasks, _ = queue_service
    first = service.submit("session-a", "block")
    second = service.submit("session-b", "second")

    service.start()
    assert agent.started.wait(1)
    assert agent.calls == ["block"]
    assert tasks.get_task(second.id).status == "queued"

    agent.release.set()
    _wait_for(lambda: tasks.get_task(second.id).status == "completed")

    assert agent.calls == ["block", "second"]
    assert agent.max_active == 1


def test_approval_holds_the_worker_until_the_same_task_is_resolved(queue_service) -> None:
    service, agent, tasks, _ = queue_service
    awaiting = service.submit("session-a", "approval")
    later = service.submit("session-b", "later")

    service.start()
    _wait_for(lambda: tasks.get_task(awaiting.id).status == "awaiting_approval")
    assert agent.calls == ["approval"]
    assert tasks.get_task(later.id).status == "queued"

    approved = service.resolve_approval(awaiting.id, "call-1", True)
    assert approved.status == "running"
    _wait_for(lambda: tasks.get_task(later.id).status == "completed")

    assert agent.resolved == [("session-a", "call-1", True)]
    assert agent.calls == ["approval", "later"]
    assert tasks.get_task(awaiting.id).status == "completed"


def test_cancel_queued_job_removes_it_without_starting_agent(queue_service) -> None:
    service, agent, tasks, queue = queue_service
    queued = service.submit("session-a", "never-start")

    stopped = service.cancel(queued.id)

    assert stopped.status == "stopped"
    assert queue.load() == []
    service.start()
    time.sleep(0.05)
    assert agent.calls == []


def test_queued_cancel_linearizes_before_worker_claim_and_never_runs_agent(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks")
    queue = QueueRepository(tmp_path / "queue")
    agent = ControlledAgentService()
    service = BlockingRemovalTaskQueueService(agent, tasks, queue)
    queued = service.submit("session-a", "never-start")

    cancellation = threading.Thread(target=service.cancel, args=(queued.id,))
    cancellation.start()
    assert service.removal_entered.wait(1)
    starter = threading.Thread(target=service.start)
    starter.start()
    # The previous implementation released the service lock before removal,
    # allowing this worker to claim and run the job at this point.  The fixed
    # implementation keeps it blocked until removal and stop are committed.
    time.sleep(0.05)
    service.release_removal.set()
    cancellation.join(timeout=1)
    starter.join(timeout=1)
    assert not cancellation.is_alive()
    assert not starter.is_alive()
    time.sleep(0.05)
    service.stop()

    assert tasks.get_task(queued.id).status == "stopped"
    assert agent.calls == []


def test_submit_fails_created_task_when_queue_ledger_write_fails(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks")
    queue = FailingSaveQueueRepository(tmp_path / "queue")
    service = TaskQueueService(ControlledAgentService(), tasks, queue)

    with pytest.raises(QueueLedgerError, match="simulated queue ledger failure"):
        service.submit("session-a", "cannot be persisted")

    created = tasks.list_tasks()
    assert len(created) == 1
    assert created[0].status == "failed"


def test_submit_and_cancel_cannot_leave_a_stopped_task_in_the_queue_ledger(tmp_path) -> None:
    tasks = BlockingCreateTaskCenterService(tmp_path / "tasks")
    queue = QueueRepository(tmp_path / "queue")
    service = TaskQueueService(ControlledAgentService(), tasks, queue)
    submitted: list[object] = []

    submission = threading.Thread(
        target=lambda: submitted.append(service.submit("session-a", "race-free submit"))
    )
    submission.start()
    assert tasks.created.wait(1)
    assert tasks.last_task_id is not None

    cancellation = threading.Thread(target=service.cancel, args=(tasks.last_task_id,))
    cancellation.start()
    time.sleep(0.05)
    tasks.release.set()
    submission.join(timeout=1)
    cancellation.join(timeout=1)

    assert not submission.is_alive()
    assert not cancellation.is_alive()
    task_id = tasks.last_task_id
    assert tasks.get_task(task_id).status == "stopped"
    assert all(job.task_id != task_id for job in queue.load())
    assert len(submitted) == 1


def test_worker_continues_to_later_jobs_when_completed_job_cleanup_fails_once(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks")
    queue = FailFirstRemovalQueueRepository(tmp_path / "queue")
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    first = service.submit("session-a", "first")
    second = service.submit("session-b", "second")
    service.start()
    try:
        _wait_for(lambda: tasks.get_task(second.id).status == "completed")
        assert tasks.get_task(first.id).status == "completed"
        assert agent.calls == ["first", "second"]
        # The first active record was intentionally retained after the failed
        # cleanup, so a later process start can apply normal recovery rules.
        assert any(job.task_id == first.id and job.state == "active" for job in queue.load())
    finally:
        service.stop()


def test_worker_retries_a_failed_claim_and_executes_the_queued_job(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks")
    queue = FailFirstClaimQueueRepository(tmp_path / "queue")
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    queued = service.submit("session-a", "after-claim-retry")
    service.start()
    try:
        _wait_for(lambda: tasks.get_task(queued.id).status == "completed")
        assert agent.calls == ["after-claim-retry"]
        assert queue.save_calls >= 3
    finally:
        service.stop()


def test_cancel_awaiting_job_discards_pending_approval_and_unblocks_worker(queue_service) -> None:
    service, agent, tasks, queue = queue_service
    waiting = service.submit("session-a", "approval")

    service.start()
    _wait_for(lambda: tasks.get_task(waiting.id).status == "awaiting_approval")
    stopped = service.cancel(waiting.id)
    _wait_for(lambda: stopped.id not in {job.task_id for job in queue.load()})

    assert stopped.status == "stopped"
    assert agent.cancelled == [("session-a", "call-1")]


def test_running_cancel_is_cooperative_and_cleans_up_after_agent_returns(queue_service) -> None:
    service, agent, tasks, queue = queue_service
    running = service.submit("session-a", "block")

    service.start()
    assert agent.started.wait(1)
    requested = service.cancel(running.id)
    assert requested.status == "running"
    assert requested.events[-1].type == "stop_requested"

    agent.release.set()
    _wait_for(lambda: tasks.get_task(running.id).status == "stopped")
    assert running.id not in {job.task_id for job in queue.load()}


def test_startup_recovers_active_job_but_keeps_queued_job_available(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks", recover_unfinished=False)
    queue = QueueRepository(tmp_path / "queue")
    active_task = tasks.create_queued_task("old", "old active")
    tasks.start(active_task.id)
    queued_task = tasks.create_queued_task("new", "block")
    queue.save([
        QueueJob(
            task_id=active_task.id,
            session_id="old",
            message="old active",
            created_at="2026-08-14T00:00:00+00:00",
            state="active",
        ),
        QueueJob(
            task_id=queued_task.id,
            session_id="new",
            message="block",
            created_at="2026-08-14T00:01:00+00:00",
            state="queued",
        ),
    ])
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    try:
        service.start()
        assert agent.started.wait(1)
        assert tasks.get_task(active_task.id).status == "stopped"
        assert tasks.get_task(active_task.id).events[-1].label == "服务重启，执行未完成"
        assert all(job.task_id != active_task.id for job in queue.load())
        assert tasks.get_task(queued_task.id).status == "running"
    finally:
        agent.release.set()
        service.stop()


def test_startup_requeues_active_ledger_entry_when_task_never_started(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks", recover_unfinished=False)
    queue = QueueRepository(tmp_path / "queue")
    queued_task = tasks.create_queued_task("session", "crash-window")
    queue.save([
        QueueJob(
            task_id=queued_task.id,
            session_id="session",
            message="crash-window",
            created_at="2026-08-14T00:00:00+00:00",
            state="active",
        )
    ])
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    try:
        service.start()
        _wait_for(lambda: tasks.get_task(queued_task.id).status == "completed")
        assert agent.calls == ["crash-window"]
    finally:
        service.stop()


def test_startup_fails_orphaned_queue_task_that_has_no_durable_job(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks", recover_unfinished=False)
    queue = QueueRepository(tmp_path / "queue")
    orphan = tasks.create_queued_task("session", "missing original message")
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    try:
        service.start()
        _wait_for(lambda: tasks.get_task(orphan.id).status == "failed")
        assert agent.calls == []
        assert queue.load() == []
    finally:
        service.stop()


def test_startup_removes_queued_ledger_record_for_already_stopped_task(tmp_path) -> None:
    tasks = TaskCenterService(tmp_path / "tasks", recover_unfinished=False)
    queue = QueueRepository(tmp_path / "queue")
    stopped = tasks.create_queued_task("session", "cancelled before crash")
    tasks.stop(stopped.id)
    queue.save([
        QueueJob(
            task_id=stopped.id,
            session_id="session",
            message="cancelled before crash",
            created_at="2026-08-14T00:00:00+00:00",
            state="queued",
        )
    ])
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    try:
        service.start()
        _wait_for(lambda: queue.load() == [])
        assert tasks.get_task(stopped.id).status == "stopped"
        assert agent.calls == []
    finally:
        service.stop()


def test_worker_continues_when_provider_and_first_failure_marker_both_fail(tmp_path) -> None:
    tasks = FailFirstTaskCenterFailureService(tmp_path / "tasks")
    queue = QueueRepository(tmp_path / "queue")
    agent = ControlledAgentService()
    service = TaskQueueService(agent, tasks, queue)
    failed_marker = service.submit("session-a", "provider-error")
    later = service.submit("session-b", "later")
    service.start()
    try:
        _wait_for(lambda: tasks.get_task(later.id).status == "completed")
        assert agent.calls == ["provider-error", "later"]
        assert tasks.get_task(failed_marker.id).status == "running"
        assert any(job.task_id == failed_marker.id and job.state == "active" for job in queue.load())
    finally:
        service.stop()


def test_queue_position_and_ledger_shape_remain_minimal(queue_service) -> None:
    service, _, _, queue = queue_service
    first = service.submit("session-a", "first")
    second = service.submit("session-b", "second")

    assert service.queue_position(first.id) == 1
    assert service.queue_position(second.id) == 2
    assert service.queue_position("missing") is None
    assert [set(job.to_dict()) for job in queue.load()] == [
        {"task_id", "session_id", "message", "created_at", "state"},
        {"task_id", "session_id", "message", "created_at", "state"},
    ]


def test_queue_position_ignores_active_records_when_numbering_queued_jobs(queue_service) -> None:
    service, _, _, queue = queue_service
    active = QueueJob(
        task_id="active-task",
        session_id="session-a",
        message="active",
        created_at="2026-08-14T00:00:00+00:00",
        state="active",
    )
    first = QueueJob(
        task_id="queued-first",
        session_id="session-b",
        message="first",
        created_at="2026-08-14T00:01:00+00:00",
        state="queued",
    )
    second = QueueJob(
        task_id="queued-second",
        session_id="session-c",
        message="second",
        created_at="2026-08-14T00:02:00+00:00",
        state="queued",
    )
    queue.save([active, first, second])

    assert service.queue_position(active.task_id) is None
    assert service.queue_position(first.task_id) == 1
    assert service.queue_position(second.task_id) == 2
