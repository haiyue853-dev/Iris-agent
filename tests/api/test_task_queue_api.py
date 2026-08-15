from __future__ import annotations

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.repository import QueueLedgerError
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


class RecordingQueue:
    def __init__(self, task_center: TaskCenterService) -> None:
        self.task_center = task_center
        self.submissions: list[tuple[str, str]] = []
        self.approvals: list[tuple[str, str, bool]] = []
        self.cancelled: list[str] = []
        self.positions: dict[str, int | None] = {}

    def submit(self, session_id: str, message: str):
        self.submissions.append((session_id, message))
        return self.task_center.create_queued_task(session_id, message)

    def resolve_approval(self, task_id: str, call_id: str, approved: bool):
        self.approvals.append((task_id, call_id, approved))
        return self.task_center.get_task(task_id)

    def cancel(self, task_id: str):
        self.cancelled.append(task_id)
        return self.task_center.stop(task_id)

    def queue_position(self, task_id: str) -> int | None:
        return self.positions.get(task_id)


class UnavailableQueue(RecordingQueue):
    error = QueueLedgerError(r"unable to read C:\private\私有问题")

    def submit(self, session_id: str, message: str):
        raise self.error

    def resolve_approval(self, task_id: str, call_id: str, approved: bool):
        raise self.error

    def cancel(self, task_id: str):
        raise self.error

    def queue_position(self, task_id: str) -> int | None:
        raise self.error


class PositionReadFailsQueue(RecordingQueue):
    def queue_position(self, task_id: str) -> int | None:
        raise QueueLedgerError("position lookup unavailable")


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    task_center = TaskCenterService(tmp_path / "tasks")
    queue = RecordingQueue(task_center)
    return TestClient(create_app(agent, sessions, task_center=task_center, task_queue=queue)), sessions, task_center, queue


def _unavailable_client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    task_center = TaskCenterService(tmp_path / "tasks")
    queue = UnavailableQueue(task_center)
    client = TestClient(
        create_app(agent, sessions, task_center=task_center, task_queue=queue),
        raise_server_exceptions=False,
    )
    return client, sessions, task_center


def _position_read_failure_client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    task_center = TaskCenterService(tmp_path / "tasks")
    queue = PositionReadFailsQueue(task_center)
    return TestClient(create_app(agent, sessions, task_center=task_center, task_queue=queue)), sessions, task_center, queue


def test_submit_returns_accepted_safe_task_summary_without_persisting_user_message(tmp_path):
    client, sessions, task_center, queue = _client(tmp_path)
    session = sessions.create("chat")

    response = client.post("/api/tasks", json={"session_id": session.id, "message": "私有问题"})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "message" not in response.json()
    assert "私有问题" not in response.text
    task_id = response.json()["id"]
    assert "私有问题" not in client.get("/api/tasks").text
    assert "私有问题" not in client.get(f"/api/tasks/{task_id}").text
    assert "私有问题" not in (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")
    assert task_center.get_task(task_id).request_summary == "后台任务"
    assert queue.submissions == [(session.id, "私有问题")]


def test_list_and_detail_include_queue_position(tmp_path):
    client, sessions, task_center, queue = _client(tmp_path)
    task = task_center.create_queued_task(sessions.create("chat").id, "private")
    queue.positions[task.id] = 2

    listed = client.get("/api/tasks")
    detail = client.get(f"/api/tasks/{task.id}")

    assert listed.status_code == 200
    assert listed.json()["tasks"][0]["queue_position"] == 2
    assert detail.status_code == 200
    assert detail.json()["queue_position"] == 2


def test_cancel_and_approval_delegate_to_queue(tmp_path):
    client, sessions, task_center, queue = _client(tmp_path)
    task = task_center.create_queued_task(sessions.create("chat").id, "private")

    cancelled = client.delete(f"/api/tasks/{task.id}")
    approved = client.post(f"/api/tasks/{task.id}/tool-approvals/call-1", json={"approved": True})

    assert cancelled.status_code == 200
    assert queue.cancelled == [task.id]
    assert approved.status_code == 409
    assert queue.approvals == []


def test_terminal_task_cannot_be_cancelled_or_approved(tmp_path):
    client, sessions, task_center, _ = _client(tmp_path)
    task = task_center.create_queued_task(sessions.create("chat").id, "private")
    task_center.complete(task.id)

    assert client.delete(f"/api/tasks/{task.id}").status_code == 409
    assert client.post(f"/api/tasks/{task.id}/tool-approvals/call-1", json={"approved": True}).status_code == 409


def test_queue_ledger_failure_returns_safe_503_for_submit_and_task_reads(tmp_path):
    client, sessions, task_center = _unavailable_client(tmp_path)
    session = sessions.create("chat")
    task = task_center.create_queued_task(session.id, "private")

    responses = [
        client.post("/api/tasks", json={"session_id": session.id, "message": "私有问题"}),
        client.get("/api/tasks"),
        client.get(f"/api/tasks/{task.id}"),
    ]

    for response in responses:
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "task_queue_unavailable"
        assert "private" not in response.text
        assert "私有问题" not in response.text


def test_queue_ledger_failure_returns_safe_503_for_cancellation(tmp_path):
    client, sessions, task_center = _unavailable_client(tmp_path)
    task = task_center.create_queued_task(sessions.create("chat").id, "private")

    response = client.delete(f"/api/tasks/{task.id}")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "task_queue_unavailable"
    assert "private" not in response.text


def test_successful_writes_do_not_fail_when_follow_up_position_read_fails(tmp_path):
    client, sessions, task_center, queue = _position_read_failure_client(tmp_path)
    session = sessions.create("chat")

    submitted = client.post("/api/tasks", json={"session_id": session.id, "message": "private"})
    cancellable = task_center.create_queued_task(session.id, "private")
    cancelled = client.delete(f"/api/tasks/{cancellable.id}")
    approvable = task_center.create_queued_task(session.id, "private")
    approved = client.post(f"/api/tasks/{approvable.id}/tool-approvals/call-1", json={"approved": True})

    assert submitted.status_code == 202
    assert submitted.json()["queue_position"] is None
    assert queue.submissions == [(session.id, "private")]
    assert cancelled.status_code == 200
    assert cancelled.json()["queue_position"] is None
    assert queue.cancelled == [cancellable.id]
    assert approved.status_code == 200
    assert approved.json()["queue_position"] is None
    assert queue.approvals == [(approvable.id, "call-1", True)]
