from fastapi.testclient import TestClient
from pathlib import Path

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry
from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.task_planning.repository import JsonTaskPlanRepository
from iris_agent.task_planning.service import TaskPlanService
from iris_agent.memory.json_provider import JsonMemoryProvider
from iris_agent.memory.service import MemoryService
from iris_agent.subagents.repository import JsonSubagentRepository
from iris_agent.subagents.service import SubagentService


class EchoProvider:
    def complete(self, messages, tools):
        return ProviderResponse(content="收到")


def make_client(tmp_path):
    sessions = JsonSessionRepository(tmp_path)
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    return TestClient(create_app(service, sessions))


def test_session_and_streaming_chat(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/api/sessions", json={"name": "会话"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "你好"})
    assert response.status_code == 200
    assert '"type": "text_delta"' in response.text
    assert client.get(f"/api/sessions/{session_id}").json()["messages"][-1]["content"] == "收到"


def test_unknown_session_returns_stable_error(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/sessions/missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


def test_validation_uses_stable_error_code(tmp_path):
    response = make_client(tmp_path).post("/api/chat/stream", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


def test_lists_interview_knowledge(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    knowledge = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    knowledge.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}])
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")

    client = TestClient(create_app(service, sessions, interview_knowledge=knowledge))

    assert client.get("/api/interview-knowledge?topic=Python").json()["items"][0]["question"] == "什么是 GIL？"


def test_practices_and_marks_interview_knowledge(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    knowledge = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    knowledge.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}])
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    client = TestClient(create_app(service, sessions, interview_knowledge=knowledge))

    item = client.get("/api/interview-knowledge/practice?topic=Python").json()["item"]
    response = client.put(f"/api/interview-knowledge/{item['id']}/review", json={"review_state": "known"})

    assert response.status_code == 200
    assert response.json()["item"]["review_state"] == "known"


def test_previews_and_confirms_interview_collection(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    knowledge = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")

    class Collector:
        def preview(self, topic, *, max_sources, max_items_per_source):
            return {
                "topic": topic,
                "items": [{"question": "What is the JVM?", "answer": "The JVM executes Java bytecode across supported platforms.", "source_url": "https://example.com/java"}],
                "sources": [{"url": "https://example.com/java", "title": "Java Interview", "status": "ok", "count": 1}],
                "summary": {"sources": 1, "found": 1, "duplicates": 0},
            }

        def save(self, topic, items):
            return knowledge.save(topic, items)

    client = TestClient(create_app(service, sessions, interview_knowledge=knowledge, interview_collector=Collector()))

    preview = client.post("/api/interview-knowledge/collection-preview", json={"topic": "Java", "max_sources": 1})
    assert preview.status_code == 200
    assert preview.json()["summary"]["found"] == 1
    assert knowledge.list() == []

    saved = client.post("/api/interview-knowledge/collection-save", json={"topic": "Java", "items": preview.json()["items"]})
    assert saved.status_code == 200
    assert saved.json()["added"] == 1
    assert len(knowledge.list("Java")) == 1


def test_creates_and_runs_task_plan(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    plans = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), service)
    client = TestClient(create_app(service, sessions, task_plans=plans))
    session_id = client.post("/api/sessions", json={"name": "task"}).json()["id"]

    created = client.post("/api/task-plans", json={"session_id": session_id, "goal": "collect", "steps": [{"title": "Search", "instruction": "Find sources"}]})
    run = client.post(f"/api/task-plans/{created.json()['id']}/run-next")

    assert created.status_code == 201
    assert run.status_code == 200
    assert run.json()["task"]["status"] == "completed"


def test_delegates_task_step_to_subagent(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    subagents = SubagentService(JsonSubagentRepository(tmp_path / "subagents"), service)
    plans = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), service, subagents)
    client = TestClient(create_app(service, sessions, task_plans=plans, subagents=subagents))
    session_id = client.post("/api/sessions", json={"name": "task"}).json()["id"]
    plan = client.post("/api/task-plans", json={"session_id": session_id, "goal": "collect", "steps": [{"title": "Research", "instruction": "Find sources"}]}).json()

    response = client.post(f"/api/task-plans/{plan['id']}/steps/{plan['steps'][0]['id']}/delegate", json={"allowed_tools": []})

    assert response.status_code == 200
    assert response.json()["task"]["steps"][0]["result"] == "收到"


def test_manages_memories_with_api(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    service = AgentService(AgentLoop(EchoProvider(), ToolRegistry()), sessions, "system")
    memory = MemoryService(JsonMemoryProvider(tmp_path / "memory.json"))
    client = TestClient(create_app(service, sessions, memory=memory))

    created = client.post("/api/memories", json={"content": "Python interview preparation", "tags": ["python"]})
    found = client.get("/api/memories/search?query=Python")
    deleted = client.delete(f"/api/memories/{created.json()['id']}")

    assert created.status_code == 201
    assert found.json()["items"][0]["content"] == "Python interview preparation"
    assert deleted.status_code == 204


def test_creates_and_runs_subagent_with_allowlisted_tools(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    tools = ToolRegistry()
    tools.register(Tool("safe", "safe", {"type": "object", "properties": {}}, lambda: "ok"))
    service = AgentService(AgentLoop(EchoProvider(), tools), sessions, "system")
    subagents = SubagentService(JsonSubagentRepository(tmp_path / "subagents"), service)
    client = TestClient(create_app(service, sessions, subagents=subagents))
    parent_id = client.post("/api/sessions", json={"name": "parent"}).json()["id"]

    created = client.post("/api/subagents", json={"parent_session_id": parent_id, "title": "Research", "instruction": "Summarize", "allowed_tools": ["safe"]})
    run = client.post(f"/api/subagents/{created.json()['id']}/run")

    assert created.status_code == 201
    assert run.json()["subagent"]["status"] == "completed"


def test_chat_uses_selected_skill_as_transient_task_context(tmp_path):
    class RecordingProvider:
        def __init__(self):
            self.messages = []

        def complete(self, messages, tools):
            self.messages = messages
            return ProviderResponse(content="done")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    provider = RecordingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    bundled = Path(__file__).resolve().parents[2] / "iris_agent" / "skill_center" / "bundled"
    skills = SkillCenterService(bundled, tmp_path / "skills" / "settings.json")
    client = TestClient(create_app(service, sessions, skills=skills))
    session_id = client.post("/api/sessions", json={"name": "test"}).json()["id"]

    response = client.post("/api/chat/stream", json={"session_id": session_id, "message": "collect Python questions", "skill_id": "interview-collection"})

    assert response.status_code == 200
    assert "search_interview_sources" in provider.messages[-1].content
    assert [message.role for message in provider.messages] == ["system", "user"]
    assert [message.content for message in sessions.get(session_id).messages] == ["collect Python questions", "done"]


def test_approved_tool_call_resumes_streaming_chat(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                from iris_agent.core.models import ToolCall
                return ProviderResponse(tool_calls=[ToolCall("call-1", "write", {})])
            return ProviderResponse(content="完成")

    sessions = JsonSessionRepository(tmp_path)
    tools = ToolRegistry()
    tools.register(Tool("write", "write", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    client = TestClient(create_app(AgentService(AgentLoop(Provider(), tools), sessions, "system"), sessions))
    session_id = client.post("/api/sessions", json={"name": "会话"}).json()["id"]

    waiting = client.post("/api/chat/stream", json={"session_id": session_id, "message": "执行"})
    assert '"type": "tool_approval_requested"' in waiting.text
    resumed = client.post(f"/api/sessions/{session_id}/tool-approvals/call-1", json={"approved": True})
    assert resumed.status_code == 200
    assert '"type": "tool_finished"' in resumed.text
    assert '"content": "完成"' in resumed.text
