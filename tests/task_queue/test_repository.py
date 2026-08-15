from __future__ import annotations

import json
import multiprocessing
import os
import time
from pathlib import Path

import pytest

from iris_agent.task_queue.models import QueueJob
from iris_agent.task_queue.repository import QueueLedgerError, QueueRepository


def _append_in_transaction(root: str, start: multiprocessing.synchronize.Event, task_id: str) -> None:
    repository = QueueRepository(Path(root))
    start.wait()
    with repository.transaction():
        jobs = repository.load()
        time.sleep(0.1)
        repository.save(
            jobs
            + [
                QueueJob(
                    task_id=task_id,
                    session_id="session-1",
                    message=task_id,
                    created_at="2026-08-14T10:00:00+00:00",
                    state="queued",
                )
            ]
        )


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
def test_save_rejects_invalid_source_without_replacing_its_bytes(tmp_path, payload: bytes) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(payload)
    repository = QueueRepository(tmp_path)
    job = QueueJob(
        task_id="task-1",
        session_id="session-1",
        message="message",
        created_at="2026-08-14T10:00:00+00:00",
        state="queued",
    )

    with pytest.raises(QueueLedgerError):
        repository.save([job])

    assert path.read_bytes() == payload


@pytest.mark.parametrize("operation", ["load", "save"])
def test_non_utf8_ledger_raises_queue_ledger_error_without_replacing_source(tmp_path, operation: str) -> None:
    path = tmp_path / "queue.json"
    payload = b"\xff\xfe\x00"
    path.write_bytes(payload)
    repository = QueueRepository(tmp_path)

    with pytest.raises(QueueLedgerError):
        if operation == "load":
            repository.load()
        else:
            repository.save([])

    assert path.read_bytes() == payload


@pytest.mark.parametrize("operation", ["load", "save"])
def test_queue_ledger_directory_raises_queue_ledger_error_without_replacing_source(tmp_path, operation: str) -> None:
    path = tmp_path / "queue.json"
    path.mkdir()
    sentinel = path / "preserve-me"
    sentinel.write_text("unchanged", encoding="utf-8")
    repository = QueueRepository(tmp_path)

    with pytest.raises(QueueLedgerError):
        if operation == "load":
            repository.load()
        else:
            repository.save([])

    assert path.is_dir()
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


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


def test_transaction_keeps_lock_file_internal_and_serializes_jobs_only_to_queue_json(tmp_path) -> None:
    repository = QueueRepository(tmp_path)
    job = QueueJob(
        task_id="task-1",
        session_id="session-1",
        message="message",
        created_at="2026-08-14T10:00:00+00:00",
        state="queued",
    )

    with repository.transaction():
        repository.save([job])

    assert repository.load() == [job]
    assert json.loads((tmp_path / "queue.json").read_text(encoding="utf-8")) == {"jobs": [job.to_dict()]}
    assert (tmp_path / "queue.lock").read_bytes() == b""


@pytest.mark.skipif(os.name != "nt", reason="queue ledger cross-process locking targets Windows")
def test_concurrent_transactions_preserve_both_jobs(tmp_path) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(target=_append_in_transaction, args=(str(tmp_path), start, task_id))
        for task_id in ("task-1", "task-2")
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert {job.task_id for job in QueueRepository(tmp_path).load()} == {"task-1", "task-2"}
