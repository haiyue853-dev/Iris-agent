"""Task-center API and NDJSON lifecycle integration tests."""

import json
import asyncio
import threading

import pytest

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.api.schemas import ChatRequest
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.task_center.service import TaskCenterService
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


class TextProvider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


class RecordingTaskCenter(TaskCenterService):
    def __init__(self, root):
        super().__init__(root)
        self.touched = []

    def touch(self, task_id, **kwargs):
        self.touched.append((task_id, kwargs))
        return super().touch(task_id, **kwargs)


def _client(tmp_path, provider=None, tools=None):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    registry = tools or ToolRegistry()
    agent = AgentService(AgentLoop(provider or TextProvider(), registry), sessions, "system")
    tasks = TaskCenterService(tmp_path / "tasks")
    return TestClient(create_app(agent, sessions, task_center=tasks)), sessions, tasks


def _stream_events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_chat_stream_starts_task_and_maps_safe_tool_events(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("read-1", "read", {"path": "secret.txt"})])
            return ProviderResponse(content="done")

    tools = ToolRegistry()
    tools.register(Tool("read", "read", {"type": "object", "properties": {}}, lambda **_: "private result"))
    client, sessions, task_center = _client(tmp_path, Provider(), tools)
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]

    events = _stream_events(client.post("/api/chat/stream", json={"session_id": session_id, "message": "read the file"}))

    assert events[0]["type"] == "task_started"
    task_id = events[0]["data"]["task_id"]
    lifecycle_events = [event["type"] for event in events[1:] if event["type"] != "react_step"]
    assert lifecycle_events == ["tool_started", "tool_finished", "text_delta", "message_completed"]
    task = task_center.get_task(task_id)
    assert task is not None
    assert task.status == "completed"
    assert [event.type for event in task.events] == ["request_submitted", "tool_started", "tool_succeeded", "reply_completed"]
    raw = (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")
    assert "secret.txt" not in raw
    assert "private result" not in raw


def test_approval_stream_associates_the_same_task_and_records_decision(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {"value": "secret"})])
            return ProviderResponse(content="done")

    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda **_: "private result", requires_approval=True))
    client, sessions, task_center = _client(tmp_path, Provider(), tools)
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]

    waiting = _stream_events(client.post("/api/chat/stream", json={"session_id": session_id, "message": "write secret"}))
    task_id = waiting[0]["data"]["task_id"]
    assert waiting[-1]["type"] == "tool_approval_requested"
    resumed = _stream_events(client.post(f"/api/sessions/{session_id}/tool-approvals/write-1", json={"approved": True}))

    lifecycle_events = [event["type"] for event in resumed if event["type"] != "react_step"]
    assert lifecycle_events == ["tool_finished", "text_delta", "message_completed"]
    task = task_center.get_task(task_id)
    assert task.status == "completed"
    assert [event.type for event in task.events] == [
        "request_submitted", "tool_started", "approval_requested", "approval_approved", "tool_succeeded", "reply_completed",
    ]


def test_rejected_approval_records_a_safe_failed_tool_event(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {"value": "secret"})])
            return ProviderResponse(content="done")

    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda **_: "private", requires_approval=True))
    client, sessions, task_center = _client(tmp_path, Provider(), tools)
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]
    task_id = _stream_events(client.post("/api/chat/stream", json={"session_id": session_id, "message": "write"}))[0]["data"]["task_id"]

    resumed = _stream_events(client.post(f"/api/sessions/{session_id}/tool-approvals/write-1", json={"approved": False}))

    assert resumed[0]["type"] == "tool_finished"
    assert task_center.get_task(task_id).events[-2].type == "tool_failed"
    raw = (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")
    assert "secret" not in raw
    assert "private" not in raw


def test_text_deltas_touch_task_without_persisting_response_body(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    tasks = RecordingTaskCenter(tmp_path / "tasks")
    agent = AgentService(AgentLoop(TextProvider(), ToolRegistry()), sessions, "system")
    client = TestClient(create_app(agent, sessions, task_center=tasks))
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]

    client.post("/api/chat/stream", json={"session_id": session_id, "message": "reply"})

    assert len(tasks.touched) == 1
    assert "done" not in (tmp_path / "tasks" / "tasks.json").read_text(encoding="utf-8")


def test_task_list_filters_limits_and_detail_uses_stable_404(tmp_path):
    client, sessions, task_center = _client(tmp_path)
    first = task_center.create_task("session-a", "first")
    task_center.complete(first.id)
    second = task_center.create_task("session-b", "second")
    task_center.complete(second.id)

    listed = client.get("/api/tasks", params={"session_id": "session-a", "limit": 999})

    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()["tasks"]] == [first.id]
    assert "events" not in listed.json()["tasks"][0]
    detail = client.get(f"/api/tasks/{first.id}")
    assert detail.status_code == 200
    assert detail.json()["events"][-1]["type"] == "reply_completed"
    missing = client.get("/api/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "task_not_found"


def test_closing_chat_stream_marks_started_task_stopped(tmp_path):
    client, sessions, task_center = _client(tmp_path)
    session = sessions.create("chat")
    route = next(route for route in client.app.routes if getattr(route, "path", None) == "/api/chat/stream")
    response = route.endpoint(ChatRequest(session_id=session.id, message="stop me"))

    async def consume_then_close():
        first = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return json.loads(first)

    first = asyncio.run(consume_then_close())
    assert first["type"] == "task_started"
    assert task_center.get_task(first["data"]["task_id"]).status == "stopped"


def test_duplicate_concurrent_approval_does_not_change_completed_task(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {})])
            return ProviderResponse(content="done")

    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    client, sessions, task_center = _client(tmp_path, Provider(), tools)
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]
    task_id = _stream_events(client.post("/api/chat/stream", json={"session_id": session_id, "message": "write"}))[0]["data"]["task_id"]
    barrier = threading.Barrier(3)
    responses = []

    def approve():
        barrier.wait()
        responses.append(client.post(f"/api/sessions/{session_id}/tool-approvals/write-1", json={"approved": True}))

    workers = [threading.Thread(target=approve) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()

    assert task_center.get_task(task_id).status == "completed"
    assert "execution_failed" not in [event.type for event in task_center.get_task(task_id).events]


def test_approval_failure_clears_association_before_a_retry(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {})])

    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    client, sessions, task_center = _client(tmp_path, Provider(), tools)
    session_id = client.post("/api/sessions", json={"name": "chat"}).json()["id"]
    task_id = _stream_events(client.post("/api/chat/stream", json={"session_id": session_id, "message": "write"}))[0]["data"]["task_id"]

    original = task_center.record_approval
    task_center.record_approval = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    failed = _stream_events(client.post(f"/api/sessions/{session_id}/tool-approvals/write-1", json={"approved": True}))
    task_center.record_approval = original

    assert failed[-1]["data"]["code"] == "internal_error"
    assert task_center.get_task(task_id).status == "failed"

    # A retry reaches AgentService's already-consumed approval and cannot mutate
    # the terminal task through stale task-center associations.
    retried = _stream_events(client.post(f"/api/sessions/{session_id}/tool-approvals/write-1", json={"approved": True}))
    assert retried[-1]["data"].get("code") != "internal_error"


def test_closing_waiting_approval_cancels_agent_pending_call(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(tool_calls=[ToolCall("write-1", "write", {})])

    invoked = []
    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: invoked.append(True), requires_approval=True))
    sessions = JsonSessionRepository(tmp_path / "sessions")
    task_center = TaskCenterService(tmp_path / "tasks")
    agent = AgentService(AgentLoop(Provider(), tools), sessions, "system")
    session = sessions.create("chat")
    lifecycle_events = [event.type for event in agent.run(session.id, "write") if event.type != "react_step"]
    assert lifecycle_events == ["tool_started", "tool_approval_requested"]

    assert agent.cancel_tool_approval(session.id, "write-1")
    assert not agent.cancel_tool_approval(session.id, "write-1")
    assert invoked == []
    with pytest.raises(Exception):
        list(agent.resolve_tool_approval(session.id, "write-1", True))
