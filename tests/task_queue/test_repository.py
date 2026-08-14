from __future__ import annotations

import json

import pytest

from iris_agent.task_queue.models import QueueJob
from iris_agent.task_queue.repository import QueueLedgerError, QueueRepository


def test_save_and_load_round_trip_preserves_fifo_order_and_messages(tmp_path) -> None:
    repository = QueueRepository(tmp_path)
    first = QueueJob(
        task_id="task-1",
        session_id="session-1",
        message="first message",
        created_at="2026-08-14T10:00:00+00:00",
        state="queued",
    )
    second = QueueJob(
        task_id="task-2",
        session_id="session-2",
        message="second message",
        created_at="2026-08-14T10:01:00+00:00",
        state="queued",
    )

    repository.save([first, second])

    assert repository.load() == [first, second]
    assert [job.message for job in repository.load()] == ["first message", "second message"]


@pytest.mark.parametrize(
    "payload",
    [
        b"not valid json",
        json.dumps([{}]).encode(),
        json.dumps({"jobs": [{}]}).encode(),
        json.dumps(
            {
                "jobs": [
                    {
                        "task_id": "task-1",
                        "session_id": "session-1",
                        "message": "message",
                        "created_at": "2026-08-14T10:00:00+00:00",
                        "state": "complete",
                    }
                ]
            }
        ).encode(),
    ],
)
def test_invalid_ledger_payload_raises_without_overwriting_source(tmp_path, payload: bytes) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(payload)
    repository = QueueRepository(tmp_path)

    with pytest.raises(QueueLedgerError):
        repository.load()

    assert path.read_bytes() == payload


def test_to_dict_has_exactly_the_safe_persisted_keys() -> None:
    job = QueueJob(
        task_id="task-1",
        session_id="session-1",
        message="message",
        created_at="2026-08-14T10:00:00+00:00",
        state="queued",
    )

    assert job.to_dict() == {
        "task_id": "task-1",
        "session_id": "session-1",
        "message": "message",
        "created_at": "2026-08-14T10:00:00+00:00",
        "state": "queued",
    }
    assert set(job.to_dict()) == {"task_id", "session_id", "message", "created_at", "state"}


def test_active_job_round_trips() -> None:
    job = QueueJob(
        task_id="task-1",
        session_id="session-1",
        message="message",
        created_at="2026-08-14T10:00:00+00:00",
        state="active",
    )

    assert QueueJob.from_dict(job.to_dict()) == job


def test_new_job_is_queued_with_the_requested_safe_values() -> None:
    job = QueueJob.new("session-1", "message", task_id="task-1")

    assert job.task_id == "task-1"
    assert job.session_id == "session-1"
    assert job.message == "message"
    assert job.state == "queued"
    assert job.created_at
