"""A single-worker bridge between the durable queue and ``AgentService``."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic
import threading
from typing import Protocol

from iris_agent.core.models import AgentEvent
from iris_agent.task_center.models import AgentTask
from iris_agent.task_center.service import TERMINAL_STATUSES, TaskCenterService
from iris_agent.task_queue.models import QueueJob
from iris_agent.task_queue.repository import QueueRepository


class QueueAgentService(Protocol):
    """The narrow AgentService surface needed by the serial queue worker."""

    def run(self, session_id: str, user_message: str): ...

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool): ...

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool: ...


class TaskQueueService:
    """Run persisted jobs FIFO, allowing at most one Agent request at a time."""

    def __init__(
        self,
        agent_service: QueueAgentService,
        task_center: TaskCenterService,
        repository: QueueRepository,
    ) -> None:
        self.agent_service = agent_service
        self.task_center = task_center
        self.repository = repository
        self._condition = threading.Condition(threading.RLock())
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._current_task_id: str | None = None
        self._waiting: tuple[str, str, str] | None = None
        self._approval_decision: tuple[str, str, bool] | None = None
        self._cancel_requested: set[str] = set()
        self._tool_started_at: dict[tuple[str, str], float] = {}

    def submit(self, session_id: str, message: str) -> AgentTask:
        """Create a queued task and persist only its safe queue record."""
        # This lock is also held by worker claims and queued cancellation, so
        # those operations never observe the TaskCenter record without its
        # matching durable queue entry (or its terminal write-failure state).
        with self._condition:
            task = self.task_center.create_queued_task(session_id, message)
            job = QueueJob.new(session_id, message, task_id=task.id)
            try:
                with self.repository.transaction():
                    self.repository.save([*self.repository.load(), job])
            except Exception:
                # A task without a durable queue job can never be executed.
                # Keep the ledger failure as the caller-visible error while
                # making the already-created task terminal and visible.
                try:
                    self.task_center.fail(task.id)
                except Exception:
                    pass
                raise
            self._condition.notify_all()
            return task

    def start(self) -> None:
        """Recover an interrupted active job and start the sole worker."""
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._recover_active_jobs()
            self._stopping = False
            self._thread = threading.Thread(target=self._work, name="iris-task-queue", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Request cooperative shutdown; a blocked provider call is not interrupted."""
        with self._condition:
            self._stopping = True
            current = self._current_task_id
            waiting = self._waiting
            if current is not None:
                self._cancel_requested.add(current)
            self._condition.notify_all()
            worker = self._thread
        if waiting is not None:
            task_id, call_id, _ = waiting
            self.agent_service.cancel_tool_approval(self._session_id(task_id), call_id)
            self._stop_and_remove(task_id)
        elif current is not None:
            self._request_stop(current)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1)

    def resolve_approval(self, task_id: str, call_id: str, approved: bool) -> AgentTask:
        """Record a decision and let the worker resume this exact Agent request."""
        with self._condition:
            waiting = self._waiting
            if waiting is None or waiting[:2] != (task_id, call_id) or task_id in self._cancel_requested:
                raise ValueError("待确认的工具调用不存在或已处理")
            _, _, tool_name = waiting
            task = self.task_center.record_approval(task_id, call_id, tool_name, approved)
            self._approval_decision = (task_id, call_id, approved)
            self._condition.notify_all()
            return task

    def cancel(self, task_id: str) -> AgentTask:
        """Cancel a queued job immediately or a current job cooperatively."""
        task = self.task_center.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status in TERMINAL_STATUSES:
            return task

        with self._condition:
            waiting = self._waiting if self._waiting and self._waiting[0] == task_id else None
            current = self._current_task_id == task_id
            if current:
                self._cancel_requested.add(task_id)
                self._condition.notify_all()
            elif waiting is None:
                # Keep the check, queue removal, and terminal transition under
                # the worker's claim lock.  Otherwise the worker can claim a
                # job after this check and before the job is removed.
                self._remove_job(task_id)
                return self.task_center.stop(task_id)

        if waiting is not None:
            _, call_id, _ = waiting
            self.agent_service.cancel_tool_approval(task.session_id, call_id)
            return self._stop_and_remove(task_id)
        if current:
            return self._request_stop(task_id)
        raise AssertionError("unreachable queued task cancellation state")

    def queue_position(self, task_id: str) -> int | None:
        """Return a one-based FIFO position for a job that has not started."""
        position = 0
        for job in self.repository.load():
            if job.state != "queued":
                continue
            position += 1
            if job.task_id == task_id:
                return position
        return None

    def _work(self) -> None:
        while True:
            with self._condition:
                if self._stopping:
                    return
                try:
                    job = self._claim_next_job()
                except Exception:
                    # A queued job has not been claimed until its active
                    # ledger state is durably saved.  Retry that I/O boundary
                    # later without failing or otherwise changing the task.
                    self._condition.wait(timeout=0.1)
                    continue
                if job is None:
                    self._condition.wait(timeout=0.2)
                    continue
                self._current_task_id = job.task_id
            try:
                self._run_job(job)
            except Exception:
                self._fail_if_unfinished(job.task_id)
            finally:
                with self._condition:
                    cancelled = job.task_id in self._cancel_requested
                    self._cancel_requested.discard(job.task_id)
                    self._current_task_id = None
                    if self._waiting is not None and self._waiting[0] == job.task_id:
                        self._waiting = None
                    self._approval_decision = None
                    self._clear_task_timers(job.task_id)
                    self._condition.notify_all()
                if cancelled:
                    self._stop_if_unfinished(job.task_id)
                try:
                    self._remove_job(job.task_id)
                except Exception:
                    # The active record remains durable when its deletion
                    # fails.  It will be recovered on the next service start;
                    # do not sacrifice the sole worker and strand later jobs.
                    pass

    def _run_job(self, job: QueueJob) -> None:
        with self._condition:
            if job.task_id in self._cancel_requested:
                return
            task = self.task_center.get_task(job.task_id)
            if task is None or task.status != "queued":
                return
            self.task_center.start(job.task_id)
            if job.task_id in self._cancel_requested:
                return
        events = self.agent_service.run(job.session_id, job.message)
        resumed_call_id: str | None = None
        while True:
            paused = False
            for event in events:
                if self._is_cancelled(job.task_id):
                    return
                if self._map_event(job, event, resumed_call_id):
                    paused = True
                    break
            if self._is_cancelled(job.task_id):
                return
            if not paused:
                task = self.task_center.get_task(job.task_id)
                if task is not None and task.status == "running":
                    self.task_center.fail(job.task_id)
                return

            decision = self._wait_for_approval(job.task_id)
            if decision is None:
                return
            _, call_id, approved = decision
            resumed_call_id = call_id
            events = self.agent_service.resolve_tool_approval(job.session_id, call_id, approved)

    def _map_event(self, job: QueueJob, event: AgentEvent, resumed_call_id: str | None) -> bool:
        data = event.data
        if event.type == "tool_started":
            call_id = str(data["call_id"])
            self.task_center.tool_started(job.task_id, str(data["name"]))
            self._tool_started_at[(job.task_id, call_id)] = monotonic()
        elif event.type == "tool_approval_requested":
            call_id = str(data["call_id"])
            tool_name = str(data["name"])
            self.task_center.approval_requested(job.task_id, call_id, tool_name)
            with self._condition:
                self._waiting = (job.task_id, call_id, tool_name)
                self._condition.notify_all()
            return True
        elif event.type == "tool_finished":
            call_id = str(data["call_id"])
            started_at = self._tool_started_at.pop((job.task_id, call_id), None)
            duration_ms = None if started_at is None else int((monotonic() - started_at) * 1000)
            self.task_center.tool_finished(
                job.task_id,
                str(data["name"]),
                duration_ms,
                call_id=call_id if call_id == resumed_call_id else None,
                succeeded=bool(data.get("ok")),
            )
        elif event.type == "text_delta":
            self.task_center.touch(job.task_id)
        elif event.type == "message_completed":
            self.task_center.complete(job.task_id)
        elif event.type == "error":
            self.task_center.fail(job.task_id)
        return False

    def _wait_for_approval(self, task_id: str) -> tuple[str, str, bool] | None:
        with self._condition:
            while not self._stopping and task_id not in self._cancel_requested:
                decision = self._approval_decision
                if decision is not None and decision[0] == task_id:
                    self._approval_decision = None
                    self._waiting = None
                    return decision
                self._condition.wait()
            return None

    def _claim_next_job(self) -> QueueJob | None:
        with self.repository.transaction():
            jobs = self.repository.load()
            for index, job in enumerate(jobs):
                if job.state != "queued":
                    continue
                active = replace(job, state="active")
                jobs[index] = active
                self.repository.save(jobs)
                return active
        return None

    def _recover_active_jobs(self) -> None:
        with self.repository.transaction():
            jobs = self.repository.load()
            recovered_jobs: list[QueueJob] = []
            changed = False
            for job in jobs:
                if job.state != "active":
                    recovered_jobs.append(job)
                    continue
                task = self.task_center.get_task(job.task_id)
                if task is not None and task.status == "queued":
                    # The process died after making the ledger active but
                    # before TaskCenter.start().  This job never began, so
                    # put it back at the same FIFO position.
                    recovered_jobs.append(replace(job, state="queued"))
                    changed = True
                elif task is not None and task.status in {"running", "awaiting_approval"}:
                    self.task_center.recover_interrupted(job.task_id)
                    changed = True
                else:
                    # Terminal or missing tasks cannot be resumed; discard
                    # only their stale active ledger entry.
                    changed = True
            if changed:
                self.repository.save(recovered_jobs)

    def _remove_job(self, task_id: str) -> None:
        with self.repository.transaction():
            jobs = self.repository.load()
            updated = [job for job in jobs if job.task_id != task_id]
            if len(updated) != len(jobs):
                self.repository.save(updated)

    def _session_id(self, task_id: str) -> str:
        task = self.task_center.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task.session_id

    def _request_stop(self, task_id: str) -> AgentTask:
        task = self.task_center.get_task(task_id)
        if task is None or task.status in TERMINAL_STATUSES:
            return task  # type: ignore[return-value]
        return self.task_center.request_stop(task_id)

    def _stop_and_remove(self, task_id: str) -> AgentTask:
        stopped = self._stop_if_unfinished(task_id)
        self._remove_job(task_id)
        return stopped

    def _stop_if_unfinished(self, task_id: str) -> AgentTask:
        task = self.task_center.get_task(task_id)
        if task is None or task.status in TERMINAL_STATUSES:
            return task  # type: ignore[return-value]
        return self.task_center.stop(task_id)

    def _fail_if_unfinished(self, task_id: str) -> None:
        task = self.task_center.get_task(task_id)
        if task is not None and task.status not in TERMINAL_STATUSES:
            self.task_center.fail(task_id)

    def _is_cancelled(self, task_id: str) -> bool:
        with self._condition:
            return self._stopping or task_id in self._cancel_requested

    def _clear_task_timers(self, task_id: str) -> None:
        for key in [key for key in self._tool_started_at if key[0] == task_id]:
            self._tool_started_at.pop(key, None)
